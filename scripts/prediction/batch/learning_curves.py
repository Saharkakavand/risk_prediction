
import collections
import h5py
import numpy as np
np.set_printoptions(suppress=True, precision=6, threshold=10000)
import os
import sys
import tensorflow as tf

import matplotlib
backend = 'Agg' if sys.platform == 'linux' else 'TkAgg'
matplotlib.use(backend)
import matplotlib.pyplot as plt

sys.path.append('../../prediction/')
sys.path.append('../../prediction/neural_networks/')

import batch.dataset_loaders
import neural_networks.updated_network

def load_data(
        filepath, 
        target_index=4, 
        timesteps=None, 
        debug_size=None):
    data = batch.dataset_loaders.risk_dataset_loader(
        filepath, 
        target_index=target_index, 
        timesteps=timesteps, 
        shuffle=True,
        debug_size=debug_size
    )
    data['y_train'] = np.hstack((1-data['y_train'], data['y_train']))
    data['y_val'] = np.hstack((1-data['y_val'], data['y_val']))

    return data

def plot_samples_size_loss_type(stats, timestep_range):
    plt.figure(figsize=(16,4))
    plt.subplot(1,2,1)
    plt.title('learning curves for range: {}'.format(timestep_range))
    plt.xlabel('Number of Samples in Training Set')
    plt.ylabel('Loss')
    plt.subplot(1,2,2)
    plt.title('nonzero learning curves for range: {}'.format(timestep_range))
    plt.xlabel('Number of Samples in Training Set')
    plt.ylabel('Loss')

    for sample_size, sample_size_stats in stats.items():
        for loss_type, loss_values in sample_size_stats.items():
            if 'nonzero' in loss_type:
                plt.subplot(1,2,2)
            else:
                plt.subplot(1,2,1)
                
            mean = np.mean(loss_values)
            std_err = np.std(loss_values) / np.sqrt(len(loss_values))
            
            c = 'red' if 'val' in loss_type else 'blue'
            
            plt.errorbar(sample_size, mean, yerr=std_err, fmt='--o', c=c)

def plot_stats(filepath_template, stats):
    range_keys = list(reversed(sorted(stats.keys())))
    for (s,e) in range_keys:
        plot_samples_size_loss_type(stats[(s,e)], (s,e))
        plt.savefig(filepath_template.format('{}_{}'.format(s,e)))
        plt.clf()

def compute_ce_loss(probs, true, thresh=1e-8):
    probs[probs<thresh] = thresh
    probs[probs > 1-thresh] = 1-thresh
    losses = -np.sum(true * np.log(probs), axis=-1)
    return np.mean(losses)

def train_model(
        data, 
        n_itr=2,
        hidden_dim=64,
        dropout_keep_prob=1.,
        n_updates=500,
        batch_size=1000,
        l2_reg=0.,
        learning_rate=2e-4):
    n_samples, timesteps, input_dim = data['x_train'].shape
    updates_per_epoch = n_samples / batch_size
    n_epochs = int(n_updates // updates_per_epoch)
    print('n_epochs ', n_epochs)
    stats = collections.defaultdict(list)
    for itr in range(n_itr):
        print('\nitr: {}'.format(itr))
        tf.reset_default_graph()
        model = neural_networks.updated_network.RNN(
            'test', 
            input_dim, 
            hidden_dim=hidden_dim,
            dropout_keep_prob=dropout_keep_prob, 
            max_len=timesteps, 
            batch_size=batch_size,
            learning_rate=learning_rate,
            l2_reg=l2_reg
        )
        sess = tf.InteractiveSession()
        sess.run(tf.global_variables_initializer())

        model.train(data, n_epochs=n_epochs, stop_early=False)

        probs, preds = model.predict(data['x_val'])
        val_loss = compute_ce_loss(probs, data['y_val'])
        stats['val_loss'].append(val_loss)

        idxs = np.where(data['y_val'][:,1] > 0)[0]
        probs, preds = model.predict(data['x_val'][idxs])
        val_loss_nonzero = compute_ce_loss(probs, data['y_val'][idxs])
        stats['val_loss_nonzero'].append(val_loss_nonzero)
        
        probs, preds = model.predict(data['x_train'])
        train_loss = compute_ce_loss(probs, data['y_train'])
        stats['train_loss'].append(train_loss)
        
        idxs = np.where(data['y_train'][:,1] > 0)[0]
        probs, preds = model.predict(data['x_train'][idxs])
        train_loss_nonzero = compute_ce_loss(probs, data['y_train'][idxs])
        stats['train_loss_nonzero'].append(train_loss_nonzero)

    return stats

def learning_curve(
        data,
        n_steps=6,
        min_samples=1000):
    
    # compute sizes
    max_samples = data['x_train'].shape[0]
    sizes = np.geomspace(min_samples, max_samples, n_steps).astype(int)
    sizes[-1] = max_samples

    # copy data again, this time so the number of training samples can vary
    data['base_x_train'] = np.copy(data['x_train'])
    data['base_y_train'] = np.copy(data['y_train'])

    # collect stats in dict
    stats = dict()

    # for each size in the set of sizes, train on that size of data
    for size in sizes:
        print('\nsample size: {}'.format(size))
        data['x_train'] = np.copy(data['base_x_train'][:size])
        data['y_train'] = np.copy(data['base_y_train'][:size])

        # train on the data, returning stats about the trained model
        stats[size] = train_model(data)

    return stats

def learning_curves(
        data, 
        timestep_ranges=[(35,40),(0,5)]):
    '''
    For each of the provided ranges, select those timesteps and then compute
    a learning curve varying the data according to the timesteps
    '''
    # copy this data so that we can slice what is in the data dict for 
    # passing to the train function 
    base_x_train = np.copy(data['x_train'])
    base_x_val = np.copy(data['x_val'])

    # collect stats in this dictionary, indexed first by the range 
    stats = dict()

    # for each timestep range, compute a learning curve
    # not that larger values of timesteps are more in the future
    # i.e., shape = (n_samples, timesteps, input_dim), and timesteps 
    # moves from past to future
    for (s,e) in timestep_ranges:
        print('\ntimestep range start: {} end: {}'.format(s,e))
        data['x_train'] = np.copy(base_x_train[:,s:e])
        data['x_val'] = np.copy(base_x_val[:,s:e])
        stats[(s,e)] = learning_curve(data)

    return stats

def main():
    filepath = '../../../data/datasets/ngsim_5_sec_40_feature_timesteps.h5'
    data = load_data(filepath, debug_size=None)
    stats = learning_curves(data)
    output_filepath = '../../../data/datasets/learning_curve_stats.npy'
    np.save(output_filepath, stats)
    viz_filepath = '../../../data/visualizations/learning_curves_{}.png'
    plot_stats(viz_filepath, stats)

if __name__ == '__main__':
    main()