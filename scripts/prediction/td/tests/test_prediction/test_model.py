
import numpy as np
import os
import sys
import tensorflow as tf
import unittest

path = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
sys.path.append(os.path.abspath(path))
path = os.path.join(os.path.dirname(__file__), os.pardir)
sys.path.append(os.path.abspath(path))

from prediction import model
from test_config import TestConfig

class TestLSTMPredictor(unittest.TestCase):

    def setUp(self):
        # reset graph before each test case
        tf.set_random_seed(1)
        np.random.seed(1)
        tf.reset_default_graph()

    def test_model_losses(self):
        config = TestConfig()
        config.hidden_layer_sizes = [32]
        config.value_dim = 1
        config.learning_rate = 5e-3
        
        # simple dataset, learn to output the sum
        n_samples = 10
        n_timesteps = 4
        input_dim = 1
        x = np.random.rand(n_samples, n_timesteps, input_dim)
        y = np.ones((n_samples, n_timesteps)) * 0.5

        for loss_type in ['mse','ce']:
            tf.reset_default_graph()
            with tf.Session() as session:
                predictor = model.LSTMPredictor((input_dim,), config)
                target_placeholder = tf.placeholder(tf.float32, [None, 1], 'target')
                if loss_type == 'mse':
                    loss = tf.reduce_sum((predictor.vf - target_placeholder) ** 2)
                elif loss_type == 'ce':
                    yt = target_placeholder
                    yp = predictor.vf
                    loss = tf.reduce_sum((yt * -tf.log(tf.nn.sigmoid(yp)) 
                            + (1 - yt) * -tf.log(1 - tf.nn.sigmoid(yp))))
                opt = tf.train.AdamOptimizer(config.learning_rate)
                train_op = opt.minimize(loss)
                session.run(tf.global_variables_initializer())

                def run_sample(p, x, y, state_in, train=True):
                    feed_dict = {
                        p.x: x,
                        target_placeholder: y,
                        p.dropout_keep_prob_ph: 1.,
                        p.state_in[0]: state_in[0],
                        p.state_in[1]: state_in[1],
                    }
                    outputs_list = [loss]
                    if train:
                        outputs_list += [train_op]
                    fetched = session.run(outputs_list, feed_dict=feed_dict)
                    
                    if train:
                        val_loss, _ = fetched
                    else:
                        val_loss = fetched[0]
                    return val_loss

                n_epochs = 100
                n_train = int(n_samples * .8)
                n_val = n_samples - n_train
                verbose = False
                for epoch in range(n_epochs):

                    # train
                    train_loss_mean = 0
                    for sidx in range(n_train):
                        train_loss = run_sample(
                            predictor,
                            x[sidx,:,:], 
                            y[sidx].reshape(-1,1),
                            predictor.state_init
                        )
                        train_loss_mean += train_loss / n_train
                    
                    # val
                    val_loss_mean = 0
                    for sidx in range(n_val):
                        val_loss = run_sample(
                                predictor,
                                x[sidx,:,:], 
                                y[sidx].reshape(-1,1),
                                predictor.state_init,
                                train=False
                            )
                        val_loss_mean += val_loss / n_val

                        value = predictor.value(
                            x[sidx,:,:], 
                            predictor.state_init[0], 
                            predictor.state_init[1],
                            sequence=True
                        )
                        if loss_type == 'ce':
                            value = 1 / (1 + np.exp(-value))
                        # print('x: {}\ny: {}\ny_pred: {}\n'.format(
                        #     x[sidx,:,:], y[sidx].reshape(-1,1), value))
                        # input()
                    
                    # report
                    if verbose:
                        print('epoch: {} / {}\ttrain loss: {}\tval loss: {}'.format(
                                epoch, n_epochs, train_loss_mean, val_loss_mean))

                self.assertTrue(np.abs(value - .5) < 1e-2)

    def test_full_sequence_prediction(self):
        config = TestConfig()
        config.hidden_layer_sizes = [32,32]
        config.value_dim = 1
        config.learning_rate = 1e-3
        
        # simple dataset, learn to output the sum
        n_samples = 100
        n_timesteps = 4
        input_dim = 1
        x = np.random.rand(n_samples, n_timesteps, input_dim)
        y = np.sum(x, axis=(1, 2)).reshape(-1, 1)

        with tf.Session() as session:
            predictor = model.LSTMPredictor((input_dim,), config)
            target_placeholder = tf.placeholder(tf.float32, [None, 1], 'target')
            loss = tf.reduce_sum((predictor.vf[-1] - target_placeholder) ** 2)
            opt = tf.train.AdamOptimizer(config.learning_rate)
            train_op = opt.minimize(loss)
            session.run(tf.global_variables_initializer())

            def run_sample(p, x, y, state_in, train=True):
                feed_dict = {
                    p.x: x,
                    target_placeholder: y,
                    p.dropout_keep_prob_ph: 1.,
                    p.state_in[0]: state_in[0],
                    p.state_in[1]: state_in[1],
                }
                outputs_list = [loss]
                if train:
                    outputs_list += [train_op]
                else:
                    outputs_list += [p.vf[-1]]
                fetched = session.run(outputs_list, feed_dict=feed_dict)
                
                if train:
                    val_loss, _ = fetched
                    return val_loss
                else:
                    val_loss, val_vf = fetched
                    return val_loss, val_vf

            n_epochs = 10
            n_train = int(n_samples * .8)
            n_val = n_samples - n_train
            verbose = False
            for epoch in range(n_epochs):

                # train
                train_loss_mean = 0
                for sidx in range(n_train):
                    train_loss = run_sample(
                        predictor,
                        x[sidx,:,:], 
                        y[sidx].reshape(1,-1),
                        predictor.state_init
                    )
                    train_loss_mean += train_loss / n_train
                
                # val
                val_loss_mean = 0
                for sidx in range(n_val):
                    val_loss, val_vf = run_sample(
                            predictor,
                            x[sidx,:,:], 
                            y[sidx].reshape(1,-1),
                            predictor.state_init,
                            train=False
                        )
                    val_loss_mean += val_loss / n_val
                    # print('x: {}\ny: {}\ny_pred: {}'.format(
                    #     x[sidx,:,:], y[sidx].reshape(1,-1), val_vf))
                    # input()
                
                # report
                if verbose:
                    print('epoch: {} / {}\ttrain loss: {}\tval loss: {}'.format(
                            epoch, n_epochs, train_loss_mean, val_loss_mean))

            self.assertTrue(train_loss_mean < 1e-2)
            self.assertTrue(val_loss_mean < 1e-2)

if __name__ == '__main__':
    unittest.main()