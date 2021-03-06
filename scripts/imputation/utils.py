
import collections
import h5py
import numpy as np
np.set_printoptions(suppress=True, precision=5, threshold=10000)
import os
import pandas as pd
import sklearn.dummy
import sklearn.metrics
import sys
import tensorflow as tf

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

import rnn_cells

def _build_recurrent_cell(hidden_dim, dropout_keep_prob):
    return rnn_cells.LayerNormLSTMCell(
        hidden_dim, 
        use_recurrent_dropout=True,
        dropout_keep_prob=dropout_keep_prob
    )

def compute_n_batches(n_samples, batch_size):
    n_batches = n_samples // batch_size
    if n_samples % batch_size != 0:
        n_batches += 1
    return n_batches

def compute_batch_idxs(start, batch_size, size):
    if start >= size:
        return list(np.random.randint(low=0, high=size, size=batch_size))
    
    end = start + batch_size

    if end <= size:
        return list(range(start, end))

    else:
        base_idxs = list(range(start, size))
        remainder = end - size
        idxs = list(np.random.randint(low=0, high=size, size=remainder))
        return base_idxs + idxs
       
def compute_lengths(arr):
    sums = np.sum(np.array(arr), axis=2)
    lengths = []
    for sample in sums:
        zero_idxs = np.where(sample == 0.)[0]
        if len(zero_idxs) == 0:
            lengths.append(len(sample))
        else:
            lengths.append(zero_idxs[0])
    return lengths

def maybe_mkdir(d):
    if not os.path.exists(d):
        os.mkdir(d)

def select_until_length(arr, lengths):
    values = []
    for i, l in enumerate(lengths):
        values += list(arr[i,:l])
    return np.array(values)

def classification_summary(preds, targets, name=''):
    prc, rcl, f_score, sup = sklearn.metrics.precision_recall_fscore_support(targets, preds, average=None)
    n_classes = len(prc)
    summaries = []
    for c in range(n_classes):
        summaries += [tf.Summary.Value(tag="{}/precision_class_{}".format(name, c), simple_value=prc[c])]
        summaries += [tf.Summary.Value(tag="{}/recall_class_{}".format(name, c), simple_value=rcl[c])]
        summaries += [tf.Summary.Value(tag="{}/f-score_class_{}".format(name, c), simple_value=f_score[c])]
    prc, rcl, f_score, sup = sklearn.metrics.precision_recall_fscore_support(targets, preds, average='micro')
    summaries += [tf.Summary.Value(tag="{}/f-score_overall".format(name), simple_value=f_score)]
    return tf.Summary(value=summaries)

def write_baseline_summary(lengths, targets, writer):
    valid_targets = select_until_length(targets, lengths)
    c = sklearn.dummy.DummyClassifier('stratified')
    c.fit(None, valid_targets)
    baseline_preds = c.predict(np.ones_like(valid_targets).reshape(-1,1))
    summary = classification_summary(baseline_preds, valid_targets, 'baseline')
    writer.add_summary(summary, 0)

def load_ngsim_trajectory_data(
        filepath, 
        traj_key=None,
        feature_keys=[
            'velocity',
            'relative_offset',
            'relative_heading',
            'length',
            'width',
            'lane_curvature',
            'markerdist_left',
            'markerdist_right',
            'accel',
            'jerk',
            'turn_rate_frenet',
            'angular_rate_frenet'
        ],
        target_keys=[
            'lidar_10'
        ],
        binedges=[10,15,25,50],
        max_censor_ratio=.3,
        max_len=None,
        train_ratio=.9,
        max_samples=None,
        shuffle=True,
        normalize=True,
        discretize=True,
        censor=50.):
    # select from the different roadways
    infile = h5py.File(filepath, 'r')
    if traj_key is None:
        x = np.vstack([infile[k].value for k in infile.keys()])
    else:
        x = np.copy(infile[traj_key].value)

    # enforce max_len
    if max_len is not None:
        x = x[:,:max_len,:]
    
    # pandas format for feature-based selection
    panel = pd.Panel(
        data=x, 
        minor_axis=infile.attrs['feature_names']
    )
    
    lengths = np.array(compute_lengths(panel[:,:,feature_keys]))
    n_samples, n_timesteps, input_dim = panel[:,:,feature_keys].shape

    # only a single target key implemented for now
    assert len(target_keys) == 1
    k = target_keys[0]
        
    # remove samples with too many censored values
    valid_sample_idxs = []
    for j, l in enumerate(lengths):
        invalid_idxs = np.where(panel[j,:l,k] == censor)[0]
        if len(invalid_idxs) / l < max_censor_ratio:
            valid_sample_idxs.append(j)
    valid_sample_idxs = np.array(valid_sample_idxs)
            
    # debugging size
    if max_samples is not None:
        valid_sample_idxs = valid_sample_idxs[:max_samples]
    
    # shuffle
    if shuffle:
        permute_idxs = np.random.permutation(len(valid_sample_idxs))
        valid_sample_idxs = valid_sample_idxs[permute_idxs]

    y = np.zeros((len(valid_sample_idxs), n_timesteps), dtype=int)
    lengths = lengths[valid_sample_idxs]
    x = np.array(panel[valid_sample_idxs,:,feature_keys])
    
    # discretize the targets
    y[:,:] = np.digitize(
        panel[valid_sample_idxs,:,k].T, 
        binedges, 
        right=True
    )
    
    # train / val split
    train_idx = int(len(valid_sample_idxs) * train_ratio)
    train_x = x[:train_idx]
    train_y = y[:train_idx]
    train_lengths = lengths[:train_idx]
    val_x = x[train_idx:]
    val_y = y[train_idx:]
    val_lengths = lengths[train_idx:]

    # normalize features
    if normalize:

        # compute statistics only on the nonzero elements of the train set
        nonzero_train_x = select_until_length(train_x, train_lengths)
        mean = np.mean(nonzero_train_x, axis=(0), keepdims=True)
        nonzero_train_x -= mean
        std = np.std(nonzero_train_x, axis=(0), keepdims=True) + 1e-8
        
        # normalize both train and val, and then set zero elements to zero again
        train_x = (train_x - mean) / std
        for i, l in enumerate(train_lengths):
            train_x[i,l:] = 0

        val_x = (val_x - mean) / std
        for i, l in enumerate(val_lengths):
            val_x[i,l:] = 0

    data = dict(
        train_x=train_x,
        train_y=train_y,
        train_lengths=train_lengths,
        val_x=val_x,
        val_y=val_y,
        val_lengths=val_lengths,
        feature_names=feature_keys,
        target_names=target_keys,
    )
    
    return data

