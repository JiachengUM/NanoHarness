from projects.uiagent.seatbooking.environment import AppEnvironment
from projects.uiagent.seatbooking.agent import SeatBookingAgent



def simulate_naive():
    agent = SeatBookingAgent()

    step1_query, step1_image = environment.step1()

    res1 = agent.function_step1(step1_query, step1_image)

    check_res1 = environment.check(res1, query1_gt)

    step2_query, step2_image = environment.step2()

    agent.check_step2_input(step2_query, step2_image)

    agent.function_step2(step2_query, step2_image)



def simulate():
    environment = AppEnvironment()
    agent = SeatBookingAgent()
    while True:
        action = agent.run()
        res = environment.response(action)

        if not res.succeed:
            break

        agent.to_next_step() 


if __name__ == "__main__":
    simulate()
