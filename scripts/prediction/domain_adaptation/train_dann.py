

import numpy as np
import os
import tensorflow as tf

from dann import DANN
from domain_adaptation_dataset import DomainAdaptationDataset
import utils
import visualization_utils

source_filepath = '../../../data/datasets/nov/sim2real.h5'
target_filepath = '../../../data/datasets/nov/ngsim_20_sec_1_feature_timesteps_traj_1_3_2.h5'
vis_dir = '/Users/wulfebw/Desktop/tmp/'
debug_size = 100000
batch_size = 500
n_pos_tgt_train = None
da_mode = 'unsupervised'

src, tgt = utils.load_data(
    source_filepath, 
    target_filepath, 
    debug_size=debug_size,
    remove_early_collision_idx=0,
    src_train_split=.9,
    tgt_train_split=2./3.,
    n_pos_tgt_train_samples=n_pos_tgt_train,
    target_idx=4
)

src = tgt

print(src['y_train'].shape)
print(src['y_val'].shape)
print(tgt['y_train'].shape)
print(tgt['y_val'].shape)

datasets = []
for split in ['train', 'val']:
    datasets.append(DomainAdaptationDataset(
        src['x_{}'.format(split)],
        src['y_{}'.format(split)],
        src['w_{}'.format(split)],
        tgt['x_{}'.format(split)],
        tgt['y_{}'.format(split)],
        tgt['w_{}'.format(split)],
        batch_size=batch_size
    ))
dataset, val_dataset = datasets

tf.reset_default_graph()
with tf.Session() as sess:
    model = DANN(
        input_dim=src['x_train'].shape[-1], 
        output_dim=2,
        lambda_final=0.,
        lambda_steps=200,
        dropout_keep_prob=.6,
        learning_rate=5e-4,
        encoder_hidden_layer_dims=(256, 128, 64),
        classifier_hidden_layer_dims=(64,),
        src_only_adversarial=True,
        shared_classifier=True,
        da_mode=da_mode
    )
    sess.run(tf.global_variables_initializer())
    model.train(
        dataset, 
        val_dataset=val_dataset, 
        val_every=2, 
        n_epochs=40, 
        verbose=True
    )