"""A small policy, trained with reinforcement learning, for how to proceed with a payment request.

See ``docs/AI_RL.md``. It chooses between asking, confirming and planning. It cannot approve,
submit or change anything, and its choices are limited by rules written in plain code.
"""
