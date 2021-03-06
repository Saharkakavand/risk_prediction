
from collections import defaultdict
import h5py
from imblearn.over_sampling import SMOTE
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
import os
import sklearn.metrics
import sys

def oversample(x, y, w):
    x, y_resampled = SMOTE().fit_sample(x, y)
    new_y = np.zeros((len(y_resampled), 2))
    zero_idxs = np.where(y_resampled == 0)
    one_idxs = np.where(y_resampled == 1)
    new_y[zero_idxs,0] = 1
    new_y[one_idxs, 1] = 1
    return x, new_y, np.ones(len(new_y))

def maybe_mkdir(d):
    if not os.path.exists(d):
        os.mkdir(d)

def compute_n_batches(n_samples, batch_size):
    n_batches = n_samples // batch_size
    if n_samples % batch_size != 0:
        n_batches += 1
    return n_batches

def compute_batch_idxs(start, batch_size, size, fill='random'):
    if start >= size:
        return list(np.random.randint(low=0, high=size, size=batch_size))
    
    end = start + batch_size

    if end <= size:
        return list(range(start, end))

    else:
        base_idxs = list(range(start, size))
        if fill == 'none':
            return base_idxs
        elif fill == 'random':
            remainder = end - size
            idxs = list(np.random.randint(low=0, high=size, size=remainder))
            return base_idxs + idxs
        else:
            raise ValueError('invalid fill: {}'.format(fill))

def listdict2dictlist(lst):
    dictlist = defaultdict(list)
    for d in lst:
        for k,v in d.items():
            dictlist[k].append(v)
    return dictlist

def process_epoch_stats(d, ret, missing_val=-1):
    for (k,v) in d.items():
        v = np.array(v).flatten()
        idxs = np.where(v != missing_val)[0]
        if len(idxs) > 0:
            ret[k].append(np.mean(v[idxs]))
    return ret

def process_stats(
        stats, 
        metakeys=[], 
        score_key='tgt_loss',
        agg_fn=np.max):
    # actual stats stored one level down
    res = stats['stats']

    # result dictionaries
    train = defaultdict(list)
    val = defaultdict(list)

    # aggregate
    for epoch in res.keys():

        dictlist = listdict2dictlist(res[epoch]['train'])
        train = process_epoch_stats(dictlist, train)
        dictlist = listdict2dictlist(res[epoch]['val'])
        val = process_epoch_stats(dictlist, val)

    if len(val.keys()) > 0:
        score = agg_fn(val[score_key])
    else: 
        score = -1
    ret = dict(train=train, val=val, score=score)
    for key in metakeys:
        if key in stats.keys():
            ret[key] = stats[key]
    return ret

def classification_score(probs, y):
    # the reason to take the argmax here is that for the ngsim data 
    # there are no continous data, but for simulated data the values might 
    # be continous and if that's the case then it will throw an error
    # this is also why we pass the positive class probability 
    for v in y:
        if v[0] != 0 and v[0] != 1:
            y = np.argmax(y, axis=-1)
            probs = probs[:,1]
            break
    
    prc_auc = sklearn.metrics.average_precision_score(y, probs)
    roc_auc = sklearn.metrics.roc_auc_score(y, probs)
    brier = np.mean((probs - y) ** 2)
    return prc_auc, roc_auc, brier

def compute_brier(a, b, w):
    return np.mean((a - b) ** 2 * w)

def compute_relative_error(a, b, w, eps=1e-10):
    return np.mean((np.abs(a - b) / (a + eps)) * w)

def compute_ce(a, b, w, eps=1e-16):
    b = np.clip(b, eps, 1-eps)
    one = a[:,1] * np.log(b[:,1])
    mask_idxs = np.where(a[:,1] == 0.)
    one[mask_idxs] = 0
    zero = a[:,0] * np.log(b[:,0])
    mask_idxs = np.where(a[:,0] == 0.)
    zero[mask_idxs] = 0
    ce = -np.mean((one + zero) * w)
    return ce

def y_to_binary(y, n):
    counts = (y * n).astype(int)
    ret = np.zeros((len(y), n))
    for i, c in enumerate(counts):
        ret[i,:c] = 1
    return ret.flatten()

def tile_flatten(x, n):
    return np.tile(np.reshape(x, (-1,1)), (1,n)).flatten()

def compute_avg_prc(y, scores, w, n=1):
    optimal_scores = tile_flatten(y, n)
    y = y_to_binary(y, n)
    scores = tile_flatten(scores, n)
    w = tile_flatten(w, n)
    avg_prc = sklearn.metrics.average_precision_score(y, scores, sample_weight=w)
    optimal = sklearn.metrics.average_precision_score(y, optimal_scores, sample_weight=w)
    avg_prc = avg_prc / optimal
    if np.isnan(avg_prc):
        avg_prc = 0
    return avg_prc

def evaluate(y, probs, w):
    brier = compute_brier(y[:,1], probs[:,1], w)
    rel_err = compute_relative_error(y[:,1], probs[:,1], w)
    avg_prc = compute_avg_prc(y[:,1], probs[:,1], w)
    idxs = np.where(y[:,1] > 0)[0]
    if len(idxs) > 0:
        pos_brier = compute_brier(y[idxs,1], probs[idxs,1], w[idxs])
        pos_rel_err = compute_relative_error(y[idxs,1], probs[idxs,1], w[idxs])
        pos_ce = compute_ce(y[idxs], probs[idxs], w[idxs])
    else:
        pos_brier = -1
        pos_rel_err = -1
        pos_ce = -1

    return dict(
        brier=brier,
        rel_err=rel_err,
        pos_brier=pos_brier,
        pos_rel_err=pos_rel_err,
        pos_ce=pos_ce,
        avg_prc=avg_prc
    )

def to_multiclass(y):
    ret = np.zeros((len(y), 2))
    ret[:,0] = 1-y
    ret[:,1] = y
    return ret

def load_features_targets_weights(f, target_idx, debug_size=None):
    n_samples = len(f['risk/features'])
    debug_size = n_samples if debug_size is None else debug_size

    features = f['risk/features'][:debug_size]
    targets = f['risk/targets'][:debug_size,:,target_idx]

    if 'risk/weights' in f.keys():
        weights = f['risk/weights'][:debug_size].flatten()
    else:
        weights = np.ones(n_samples)

    return features, targets, weights

def load_single_dataset(
        filepath,
        debug_size=None,
        target_idx=2,
        timestep=-1,
        start_y_timestep=101,
        end_y_timestep=None,
        remove_early_collision_idx=0):

    file = h5py.File(filepath, 'r')
    feature_names = file['risk'].attrs['feature_names']
    target_names = file['risk'].attrs['target_names'][target_idx]
    x, y, w = load_features_targets_weights(file, target_idx, debug_size)

    # convert target values from timeseries to single value
    ## optionally remove instances where there's an early collision
    if remove_early_collision_idx > 0:
        valid_idxs = np.where(y[:,:remove_early_collision_idx].sum(1) == 0)[0]
        x = x[valid_idxs]
        y = y[valid_idxs]
        w = w[valid_idxs]
    ## sum across timesteps because each timestep is already the probability
    ## of a collision occuring at that timestep, where the probability at 
    ## each timestep is mutually exclusive
    end_y_timestep = y.shape[1] if end_y_timestep is None else end_y_timestep
    y = y[:,start_y_timestep:end_y_timestep].sum(1)

    # select the timestep of the features (a single one for now)
    if len(x.shape) > 2:
        x = x[:,timestep]

    # convert y to array format
    y = to_multiclass(y)

    return dict(
        x=x, 
        y=y, 
        w=w, 
        feature_names=feature_names, 
        target_names=target_names
    )

def align_features_targets(src, tgt):
    # target values should just match
    assert src['target_names'] == tgt['target_names']

    # subselect src features to only those features also in the target set
    # need to do this in a manner such that the features align
    # accomplish this by iterating the target feature names
    # finding the src feature name that matches the current target
    # and add its index if it exists
    keep_idxs = []
    for tgt_name in tgt['feature_names']:
        for i, src_name in enumerate(src['feature_names']):
            if src_name == tgt_name:
                keep_idxs.append(i)
                break
    # subselect src features
    assert all(src['feature_names'][keep_idxs] == tgt['feature_names'])
    src['feature_names'] = src['feature_names'][keep_idxs]
    src['x'] = src['x'][...,keep_idxs]

    return src, tgt

def sample_binary_train_targets(d):
    ys = d['y_train']
    for i, (_,y) in enumerate(ys):
        if np.random.rand() < y:
            ys[i,0] = 0
            ys[i,1] = 1
        else:
            ys[i,0] = 1
            ys[i,1] = 0
    return d

def train_val_test_split(d, train_split, max_train_pos=None):
    n_samples = len(d['x'])
    tr_idx = int(train_split * n_samples)
    
    x_tr = d['x'][:tr_idx]
    y_tr = d['y'][:tr_idx]
    w_tr = d['w'][:tr_idx]
    
    val_split = (1 - train_split) / 2.
    val_idx = tr_idx + int(val_split * n_samples)
    x_val = d['x'][tr_idx:val_idx]
    y_val = d['y'][tr_idx:val_idx]
    w_val = d['w'][tr_idx:val_idx]

    x_te = d['x'][val_idx:]
    y_te = d['y'][val_idx:]
    w_te = d['w'][val_idx:]

    d.update(dict(
        x_train=x_tr,
        y_train=y_tr,
        w_train=w_tr,
        x_val=x_val,
        y_val=y_val,
        w_val=w_val,
        x_test=x_te,
        y_test=y_te,
        w_test=w_te
        )
    )
    return d

def find_n_pos_idx(x, n):
    count, i = 0, 0
    for i, v in enumerate(x):
        if v > 0:
            count += 1
        if count > n:
            break
    return i

def subselect_pos_train(d, max_train_pos):
    idx = find_n_pos_idx(d['y_train'][:,1], max_train_pos)
    d['x_train'] = d['x_train'][:idx]
    d['y_train'] = d['y_train'][:idx]
    d['w_train'] = d['w_train'][:idx]
    return d

def subselect_train(d, max_train):
    d['x_train'] = d['x_train'][:max_train]
    d['y_train'] = d['y_train'][:max_train]
    d['w_train'] = d['w_train'][:max_train]
    return d

def normalize_composite(src, tgt):
    # count samples for weighting the respective means
    n_src = len(src['x_train'])
    n_tgt = len(tgt['x_train'])
    n = n_src + n_tgt
    src_ratio = n_src / n
    tgt_ratio = n_tgt / n

    # compute mean by weighting the source and target means by their sizes
    src_mean = np.mean(src['x_train'], axis=0, keepdims=True)
    tgt_mean = np.mean(tgt['x_train'], axis=0, keepdims=True)
    mean = src_ratio * src_mean + tgt_ratio * tgt_mean

    # center the features and compute std
    src['x_train'] -= mean
    tgt['x_train'] -= mean
    src_std = np.std(src['x_train'], axis=0, keepdims=True) 
    tgt_std = np.std(tgt['x_train'], axis=0, keepdims=True)
    std = (src_std * src_ratio + tgt_std * tgt_ratio) + 1e-8

    # finish normalizing train, and normalize val and test
    src['x_train'] /= std
    tgt['x_train'] /= std

    src['x_val'] = (src['x_val'] - mean) / std
    src['x_test'] = (src['x_test'] - mean) / std
    tgt['x_val'] = (tgt['x_val'] - mean) / std
    tgt['x_test'] = (tgt['x_test'] - mean) / std

    src['mean'] = tgt['mean'] = mean
    src['std'] = tgt['std'] = std

    return src, tgt

def normalize_individual(d):
    mean = np.mean(d['x_train'], axis=0, keepdims=True)
    d['x_train'] -= mean
    std = np.std(d['x_train'], axis=0, keepdims=True) + 1e-8
    d['x_train'] /= std

    d['x_val'] = (d['x_val'] - mean) / std
    d['x_test'] = (d['x_test'] - mean) / std
    d['mean'] = mean
    d['std'] = std
    return d

def normalize(src, tgt, mode):
    if mode == 'individual':
        src = normalize_individual(src)
        tgt = normalize_individual(tgt)
    elif mode == 'composite':
        src, tgt = normalize_composite(src, tgt)
    return src, tgt

def load_data(
        src_filepath,
        tgt_filepath,
        debug_size=None,
        target_idx=2,
        timestep=-1,
        start_y_timestep=101,
        end_y_timestep=None,
        remove_early_collision_idx=0,
        src_train_split=.8,
        tgt_train_split=.5,
        n_pos_tgt_train_samples=None,
        n_tgt_train_samples=None,
        sample_tgt_train=True,
        normalize_mode='composite',
        perform_normalize=True):
    # set seed value for consistent loading
    np.random.seed(0)

    # load in the datasets
    src = load_single_dataset(
        src_filepath,
        debug_size,
        target_idx,
        timestep,
        start_y_timestep,
        end_y_timestep,
        remove_early_collision_idx
    )
    tgt = load_single_dataset(
        tgt_filepath,
        debug_size,
        target_idx,
        timestep,
        start_y_timestep,
        end_y_timestep,
        remove_early_collision_idx
    )

    # align src and tgt target and feature values
    src, tgt = align_features_targets(src, tgt)

    # split each into train, val, test sets
    src = train_val_test_split(src, src_train_split)
    tgt = train_val_test_split(tgt, tgt_train_split)

    # sample tgt train target values to binarize them
    if sample_tgt_train:
        tgt = sample_binary_train_targets(tgt)

    # subselect certain number of positive tgt train values 
    if n_pos_tgt_train_samples is not None:
        tgt = subselect_pos_train(tgt, n_pos_tgt_train_samples)
    elif n_tgt_train_samples is not None:
        tgt = subselect_train(tgt, n_tgt_train_samples)

    # normalize the datasets
    if perform_normalize:
        src, tgt = normalize(src, tgt, normalize_mode)
    
    return src, tgt

if __name__ == '__main__':
    src_filepath = '../../../data/datasets/nov/subselect_proposal_prediction_data.h5'
    tgt_filepath = '../../../data/datasets/nov/bn_train_data.h5'
    src, tgt = load_data(src_filepath, tgt_filepath)
