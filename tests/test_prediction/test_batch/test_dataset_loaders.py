
import numpy as np
import os
import sys
import unittest

path = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, 'scripts')
sys.path.append(os.path.abspath(path))
path = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, 'scripts', 'prediction', 'batch')
sys.path.append(os.path.abspath(path))

from utils import util
from prediction.batch import dataset_loaders

DEBUG_FILEPATH = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, 
    'data', 'debug.h5')

class TestRiskDatasetLoader(unittest.TestCase):

    def setUp(self):
        # commenting out because the file is out of date
        # url = "https://s3.us-east-2.amazonaws.com/autorisk/debug.h5"
        # input_filepath = os.path.abspath(DEBUG_FILEPATH)
        # util.download_if_necessary(url, input_filepath)
        pass

    def test_risk_dataset_loader(self):
        input_filepath = DEBUG_FILEPATH
        data = dataset_loaders.risk_dataset_loader(
            input_filepath, train_split=.8)
        keys = ['x_train', 'y_train', 'x_val', 'y_val']
        for k in keys:
            self.assertTrue(k in data)
        num_train = float(len(data['x_train']))
        num_val = len(data['x_val'])
        self.assertAlmostEqual(num_train / (num_train + num_val), .8, 2)

    def test_normalization(self):
        input_filepath = DEBUG_FILEPATH
        data_unnorm = dataset_loaders.risk_dataset_loader(
            input_filepath, normalize=False)
        data_norm = dataset_loaders.risk_dataset_loader(
            input_filepath, normalize=True)
        
        mean = np.mean(data_unnorm['x_train'], axis=0)
        expected = (data_unnorm['x_train'] - mean)
        std = np.std(expected, axis=0)
        std[std < 1e-8] = 1
        expected /= std

        actual = data_norm['x_train']
        np.testing.assert_array_equal(expected, actual)

    def test_sequence_normalization(self):
        x_train = np.ones(8).reshape(2,2,2)
        x_train[:,:,1] *= 2
        x_val = np.ones(8).reshape(2,2,2)
        data = {'x_train': x_train, 'x_val': x_val}

        dataset_loaders.normalize_features(data)

        self.assertEquals(data['means'].shape, (2,))
        self.assertEquals(data['stds'].shape, (2,))
        np.testing.assert_array_equal(data['means'], [1,2])
        np.testing.assert_array_equal(data['stds'], [1,1])
        self.assertEquals(data['x_train'].shape, (2,2,2))
        self.assertEquals(data['x_val'].shape, (2,2,2))

if __name__ == '__main__':
    unittest.main()