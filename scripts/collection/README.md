
<!-- MarkdownTOC -->

- [Dataset Collection](#dataset-collection)
    - [Heuristic Dataset Collection](#heuristic-dataset-collection)
    - [Bayes Net Lane Generation Dataset Collection](#bayes-net-lane-generation-dataset-collection)

<!-- /MarkdownTOC -->

# Dataset Collection
- this directory contains scripts for generating datasets
- there are a variety of datasets that can be generated
- 'heuristic' datasets are those with something heuristic about them - for example, they might rely on simple rules for how they initialize scenes
- datasets that are not heurisitc are typically generated using a method that learns from data how to e.g., initialize the scene or act within that scene

## Heuristic Dataset Collection
- to collect a basic dataset run:
```
julia run_collect_dataset.jl --num_scenarios 1 --num_monte_carlo_runs 1
```
- this will generate a dataset from a single scenario (i.e., a roadway, scene, behavior model tuple), output some information about that dataset, and save it to a file in the data directory.
- there are a number of settings that dictate the heuristic rules for generating and simulating a dataset, and `dataset_config.jl` contains the flags for setting these values

## Bayes Net Lane Generation Dataset Collection
- to collect a dataset where initial scenes are generated by a bayes net run for example
`julia run_collect_dataset.jl --generator_type joint --base_bn_filepath ../../data/bayesnets/base_test.jld`
- this will generate a dataset and save it in the data directory
- to generate a dataset with a proposal BN run something along the lines of  
`julia run_collect_dataset.jl --generator_type joint --base_bn_filepath ../../data/bayesnets/base_test.jld --base_bn_filepath ../../data/bayesnets/prop_test.jld`