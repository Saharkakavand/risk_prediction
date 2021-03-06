using AutoRisk
using Discretizers
using DataFrames
using PGFPlots

include("fit_bayes_net.jl")

const FEATURE_NAMES = [
    "relvelocity", 
    "forevelocity", 
    "foredistance", 
    "vehlength", 
    "vehwidth", 
    "aggressiveness", 
    "isattentive"
]

function visualize_stats(
        stats::DefaultDict{String, Vector{Float64}}, 
        iter::Int,
        viz_dir::String
    )
    g = GroupPlot(
            3, 3, groupStyle = "horizontal sep = 1.75cm, vertical sep = 1.5cm")
    for (fidx, feature_name) in enumerate(FEATURE_NAMES)
        a = Axis(Plots.Linear(collect(1:iter), stats[feature_name]), 
            width="8cm",
            height="8cm",
            title="$(feature_name)")
        push!(g, a)
    end
    a = Axis(Plots.Linear(collect(1:iter), stats["utilities"]), 
            width="8cm",
            height="8cm",
            title="utilities")
    push!(g, a)
    a = Axis(Plots.Linear(collect(1:iter), stats["weights"]), 
            width="8cm",
            height="8cm",
            title="weights")
    push!(g, a)

    output_filepath = joinpath(viz_dir, "iter_$(iter).pdf")
    PGFPlots.save(output_filepath, g)
end

function update_stats(
        stats::DefaultDict{String, Vector{Float64}}, 
        features::AbstractArray{Float64}, 
        utilities::AbstractArray{Float64}, 
        weights::AbstractArray{Float64}
    )
    # update feature means
    for (fidx, feature_name) in enumerate(FEATURE_NAMES)
        push!(stats[feature_name], mean(features[fidx,:]))
    end
    push!(stats["utilities"], mean(utilities))
    push!(stats["weights"], mean(weights))
end

function DataFrame(data::Array{Float64}, var_names::Vector{String})
    df = DataFrame()
    for (index, v) in enumerate(var_names)
        df[Symbol(v)] = data[index, :]
    end
    return df
end

# selects relevant features and adds to data
function extract_bn_features( 
        features::Array{Float64}, 
        feature_names::Array{String},
        index::Int
    )
    bn_features = zeros(7)
    bn_features[1:5] = Array(extract_base_features(features, feature_names))
    bn_features[6] = extract_aggressiveness(features, feature_names, 
        rand_aggressiveness_if_unavailable = false)[1]
    bn_features[7] = extract_is_attentive(features, feature_names, 
        rand_attentiveness_if_unavailable = false)[1]
    return bn_features
end

"""
Description:
    Fit a proposal BN via the cross entropy method. Basically, generate a large
    number of scenes, simulate each of them, the ones that result in the most 
    events (collisions, hard brakes) keep them and throw out the others, then
    fit a new BN to these scenes. Repeat this process until the probability of 
    the event is high enough

Args:
    - cols: vector of dataset collector objects used to simulate and eval scenes
    - y: probability of event at which to stop the process
    - max_iters: how many times to run the process max
    - N: population size
    - top_k_fraction: what fraction of scenes to keep each iteration
        e.g., .25 means keep the top 25% of the samples
    - target_indices: which of the target variables should be considered
        1 = lane change collision, 2 = rear end, etc
    - n_prior_samples: number of samples from the base BN to start out with
    - n_static_prior_samples: number of samples from the base BN to keep
        throughout training
    - weight_threshold: we throw out samples where the weight is above this threshold

Retruns:
    - Proposal Bayes net and the discretizers associated with it
"""
function run_cem(
        cols::Vector{DatasetCollector}, 
        exts::Vector{AbstractFeatureExtractor},
        y::Float64;
        max_iters::Int = 10,
        N::Int = 1000, 
        top_k_fraction::Float64 = .5, 
        target_indices::Vector{Int} = [1,2,3,4,5],
        n_prior_samples::Int = 60000,
        n_static_prior_samples::Int = 10000,
        weight_threshold::Float64 = 10.,
        output_filepath::String = "../../data/bayesnets/prop_test.jld",
        stats_filepath::String = "../../data/bayesnets/stats.jld",
        viz_dir::String = "../../data/bayesnets/viz",
        permit_diff_disc::Bool = false,
        start_target_timestep::Int = 0,
        end_target_timestep::Union{Int,Void} = nothing
    )
    # initialize
    col = cols[1]
    n_vars = length(keys(col.gen.base_bn.name_to_index))
    n_targets, target_timesteps, n_vehicles = size(col.eval.targets)
    top_k = Int(ceil(top_k_fraction * N))
    proposal_vehicle_index = get_target_vehicle_index(col.gen, col.roadway)
    if end_target_timestep == nothing
        end_target_timestep = target_timesteps
    else
        msg = "end_target_timestep ($(end_target_timestep)) must be <= target_timesteps ($(target_timesteps))"
        @assert(end_target_timestep <= target_timesteps, msg)
    end

    # derive prior values
    disc_types = get_disc_types(col.gen.base_assignment_sampler)
    discs = col.gen.base_assignment_sampler.discs
    prior = rand(col.gen.base_bn, n_prior_samples)
    prior = decode(prior, discs)
    disc_types = get_disc_types(col.gen.base_assignment_sampler)
    static_prior = rand(col.gen.base_bn, n_static_prior_samples)
    static_prior = decode(static_prior, discs)
    
    # allocate containers / single compute values
    stats = DefaultDict{String, Vector{Float64}}(Vector{Float64})
    utilities = SharedArray(Float64, N)
    weights = SharedArray(Float64, N)
    data = SharedArray(Float64, n_vars, N)
    ext_feature_names = feature_names(exts[1])
    for iter in 1:max_iters       
        # reset
        fill!(utilities, 0.)
        fill!(weights, 0.)
        fill!(data, 0.)
        
        # generate and evaluate a scene from the current bayes net
        @parallel (+) for scene_idx in 1:N

            # select the corresponding collector
            index = (scene_idx % length(cols)) + 1
            col = cols[index]
            ext = exts[index]
            
            # compute seed
            seed = (iter - 1) * N + scene_idx
            
            # sample a scene + models
            rand!(col, seed)

            # extract features
            update!(col.eval.rec, col.scene)
            pull_features!(ext, col.eval.rec, col.roadway, 
                proposal_vehicle_index, col.models)
            empty!(col.eval.rec)

            # evaluate this scene (i.e., extract targets)
            evaluate!(col.eval, col.scene, col.models, col.roadway, seed)

            # extract utilities and weights
            cur_utilities = get_targets(col.eval)
            cur_utilities = cur_utilities[target_indices, start_target_timestep:end_target_timestep, proposal_vehicle_index]
            utilities[scene_idx] = sum(cur_utilities)
            weights[scene_idx] = get_weights(col.gen)[proposal_vehicle_index][1]

            data[:, scene_idx] = extract_bn_features(
                ext.features[:], 
                ext_feature_names, 
                proposal_vehicle_index)
        end

        # select samples with weight > weight_threshold
        valid_indices = find(weights .<= weight_threshold)
        invalid_indices = find(weights .> weight_threshold)

        # update and visualize stats
        update_stats(stats, data[:, valid_indices], 
            utilities[valid_indices], weights[valid_indices])
        @spawnat 1 visualize_stats(stats, iter, viz_dir)
                
        # select top fraction of population
        # where that fraction depends on how many samples are positive
        weights[invalid_indices] = 0.
        cur_k = length(find(utilities .* weights .> 0))
        cur_k = min(top_k, cur_k)
        indices = reverse(sortperm(utilities .* weights))
        indices = indices[1:cur_k]
        # permute so that overwriting later doesn't replace only well-performing
        # samples, but rather a random set
        indices = indices[randperm(cur_k)]

        # add that set to the prior, and remove older samples
        df_data = DataFrame(data[:, indices], FEATURE_NAMES)
        prior = vcat(prior, df_data)[(cur_k + 1):end, :]
        training_data = vcat(prior, static_prior)

        # refit bayesnet and reset in the collectors
        if permit_diff_disc
            prop_bn, discs = fit_bn(training_data, disc_types)
        else
            prop_bn = fit_bn(training_data, discs)
        end

        for col in cols
            col.gen.prop_bn = prop_bn
            col.gen.prop_assignment_sampler = AssignmentSampler(discs)
        end

        # save checkpoint
        JLD.save(output_filepath, "bn", prop_bn, "discs", discs)
        JLD.save(stats_filepath, "stats", stats)

        # report progress
        unweighted_utils = mean(utilities)
        weighted_utils = mean(utilities .* weights)
        println("""
            iter: $(iter) / $(max_iters)
            weighted utilities: $(weighted_utils)
            unweighted utilities: $(unweighted_utils)
            number of samples with positive utility: $(cur_k)
        """)

        # check if the target probability has been sufficiently optimized
        # do this in an unweighted fashion
        if mean(utilities) > y
            break
        end
    end
    return col.gen.prop_bn, discs
end
