def route_next_phase(state):
    config = state["debate_config"]
    phase = state["current_phase"]
    if phase == "ANSWER" and config["depth"] >= 2:
        return "rebuttal"
    if phase == "REBUTTAL" and config["depth"] >= 3:
        return "counter"
    return "round"


def route_round(state):
    return "complete" if state["turn_number"] >= state["max_turns"] else "next"
