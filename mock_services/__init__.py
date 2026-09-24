"""Mock downstream systems for local development only.

NOT production code. One small FastAPI app emulates the three fictional systems:
- Identity Management System   -> /identity/api/v1/users/{person_id}
- Collaboration Platform       -> /collaboration/api/v1/tasks
- Notification Service         -> /notification/api/v1/notifications

Failure simulation is controlled with environment variables (read at startup) and can be
changed at runtime through /_simulation for demos.
"""
