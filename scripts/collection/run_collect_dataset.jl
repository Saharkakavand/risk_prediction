using AutoRisk
using CommandLineFlags

include("collect_dataset.jl")
include("dataset_config.jl")

function analyze_risk_dataset(output_filepath)
    dataset = h5open(output_filepath)
    features = read(dataset["risk/features"])
    targets = read(dataset["risk/targets"])
    println("avg features: $(mean(features, (2,3)))")
    avg_targets = mean(clamp(sum(targets, 2), 0, 1), 3)
    println("avg targets: $(avg_targets)")
    println("size of dataset features: $(size(features))")
    println("size of dataset targets: $(size(targets))")
    if exists(dataset, "risk/weights")
        weights = read(dataset["risk/weights"])
        inds = find(weights .!= 1.)

        if length(inds) > 0
                avg_prop_weight = mean(weights[1, inds])
                println("avg proposal weight: $(avg_prop_weight)")
                med_prop_weight = median(weights[1, inds])
                println("median proposal weight: $(med_prop_weight)")
        end
    end
end

function main()
    parse_flags!(FLAGS, ARGS)
    FLAGS["num_proc"] = max(nprocs() - 1, 1)
    pcol = build_parallel_dataset_collector(FLAGS)
    generate_dataset(pcol)
    analyze_risk_dataset(FLAGS["output_filepath"])
end

@time main()
# Profile.clear_malloc_data()
# Profile.clear()
# @profile main()
# Profile.print(format = :flat, sortedby = :time)