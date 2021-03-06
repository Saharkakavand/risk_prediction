export 
    Env,
    step,
    reset,
    observation_space_spec,
    action_space_spec,
    render,
    obs_var_names,
    reward_names

abstract Env
Base.step(env::Env) = error("Not implemented")
Base.step(env::Env, action::Int) = error("Not implemented")
Base.step(env::Env, action::Float64) = error("Not implemented")
Base.step(env::Env, action::Array{Float64}) = error("Not implemented")
Base.reset(env::Env) = error("Not implemented")
observation_space_spec(env::Env) = error("Not implemented")
action_space_spec(env::Env) = error("Not implemented")
render(env::Env) = error("Not implemented")
obs_var_names(env::Env) = error("Not implemented")
reward_names(env::Env) = error("Not implemented")