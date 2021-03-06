"""
This scripts selects same from a dataset that are associated with a likelihood
weight that is not 1. This task is performed after dataset collection for now.
"""
import argparse
import h5py
import numpy as np
import os

def copy_attrs(src, dest):
    for k in src.keys():
        try:
            v = src[k]
        except Exception as e:
            print('exception occurred during transfer of key: {}; ignoring'.format(k))
        else:
            if k.startswith('utf8_'):
                k = k.replace('utf8_', '')
                v = ''.join(chr(i) for i in v)
            elif isinstance(v, np.generic):
                v = np.asscalar(v)
            dest[k] = v

    return dest

def select_nonconstant_features(input_filepath, output_filepath, 
        batch_size=1000, check_size=10000, eps=1e-8):
    infile = h5py.File(input_filepath, 'r')
    outfile = h5py.File(output_filepath, 'w')

    # find nonzero features
    print('finding nonzero features...')
    nsamples, timesteps, feature_dim = infile['risk/features'].shape
    _, target_timesteps, target_dim = infile['risk/targets'].shape
    feature_names = infile['risk'].attrs['feature_names']
    nonzero_fidxs = []
    zero_fidxs = []
    for fidx in range(feature_dim):
        value_range = np.ptp(infile['risk/features'][:check_size,:,fidx])
        print('feature: {}\trange: {:.5f}'.format(
            feature_names[fidx], value_range))
        if value_range > eps:
            nonzero_fidxs.append(fidx)
        else:
            zero_fidxs.append(fidx)

    print('nonzero indices: {}'.format(nonzero_fidxs))
    print('zero indices: {}'.format(zero_fidxs))
    print('length nonzero: {}'.format(len(nonzero_fidxs)))
    print('zero features: {}'.format(feature_names[zero_fidxs]))
    
    # select the targets, features, weights from the proposal network
    print('transferring...')
    nonzero_feature_dim = len(nonzero_fidxs)
    outfile.create_dataset("risk/features", (nsamples, timesteps, nonzero_feature_dim))
    outfile.create_dataset("risk/targets", (nsamples, target_timesteps, target_dim))

    nbatches = int(nsamples / float(batch_size))
    if nsamples % batch_size != 0:
        nbatches += 1

    for bidx in range(nbatches):
        print('batch {} \ {}'.format(bidx, nbatches))
        s = bidx * batch_size
        e = s + batch_size
        outfile['risk/features'][s:e,:,:] = infile['risk/features'][s:e,:,nonzero_fidxs]
        outfile['risk/targets'][s:e] = infile['risk/targets'][s:e]
    
    # metadata
    if 'risk/weights' in infile.keys():
        outfile['risk/weights'] = infile['risk/weights'].value
    outfile['risk/seeds'] = infile['risk/seeds'].value
    outfile['risk/batch_idxs'] = infile['risk/batch_idxs'].value

    copy_attrs(infile['risk'].attrs, outfile['risk'].attrs)
    outfile['risk'].attrs['feature_names'] = infile['risk'].attrs['feature_names'][nonzero_fidxs]

    infile.close()
    outfile.close()

def select_proposal_samples(input_filepath, output_filepath, batch_size=1000):
    infile = h5py.File(input_filepath, 'r')
    outfile = h5py.File(output_filepath, 'w')

    # find proposal indices
    weights = infile['risk/weights']
    prop_idxs = np.where(weights[:,0] != 1.)[0]
    nsamples = len(prop_idxs)
    _, timesteps, feature_dim = infile['risk/features'].shape
    _, target_timesteps, target_dim = infile['risk/targets'].shape

    outfile.create_dataset("risk/features", (nsamples, timesteps, feature_dim))
    outfile.create_dataset("risk/targets", (nsamples, target_timesteps, target_dim))

    nbatches = int(nsamples / float(batch_size))
    if nsamples % batch_size != 0:
        nbatches += 1
    for bidx in range(nbatches):
        print('batch: {} / {}'.format(bidx, nbatches))
        s = bidx * batch_size
        e = s + batch_size
        idxs = prop_idxs[s:e]
        outfile['risk/features'][s:e,:,:] = infile['risk/features'][idxs,:,:]
        outfile['risk/targets'][s:e,:] = infile['risk/targets'][idxs,:]
        
    outfile['risk/weights'] = weights.value[prop_idxs]

    # metadata
    outfile['risk/seeds'] = infile['risk/seeds'].value
    outfile['risk/batch_idxs'] = np.arange(len(prop_idxs)).reshape(-1, 1)
    copy_attrs(infile['risk'].attrs, outfile['risk'].attrs)

    infile.close()
    outfile.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset_filepath', default='', type=str,
                            help="filepath to original dataset")
    parser.add_argument('--subselect_filepath', 
                            default='', type=str,
                            help="filepath to output feature and proposal subselected data")
    parser.add_argument('--subselect_feature_filepath', 
                            default='', type=str,
                            help="filepath to output feature subselected data")
    parser.add_argument('--subselect_proposal_filepath', 
                            default='', type=str,
                            help="filepath to output proposal subselected data")
    parser.add_argument('--subselect_proposal', 
                            action='store_true',
                            help="whether to subselect proposal samples")
    args = parser.parse_args()

    path, filename = os.path.split(args.dataset_filepath)
    if args.subselect_filepath == '':
        args.subselect_filepath = os.path.join(
            path, 'subselect_' + filename)
    if args.subselect_feature_filepath == '':
        args.subselect_feature_filepath = os.path.join(
            path, 'subselect_feature_' + filename)
    if args.subselect_proposal_filepath == '':
        args.subselect_proposal_filepath = os.path.join(
            path, 'subselect_proposal_' + filename)

    # output three datasets
    # one in which all the samples are included, but only nonconstant features 
    # are captured, a second where all features are included, but only proposal
    # samples are kept, and a third with both these conditions
    # select_nonconstant_features(args.dataset_filepath, 
    #     args.subselect_feature_filepath)

    if args.subselect_proposal:
        select_proposal_samples(args.dataset_filepath, 
            args.subselect_proposal_filepath)
        select_nonconstant_features(args.subselect_proposal_filepath, 
            args.subselect_filepath)

