# Hook Registry

This folder records when Willind capabilities are allowed to influence a session.

- `hook-routing.yaml`: broad hook timing contract.
- `skill-routing.yaml`: situation -> composed capability selection rules.

Provider-specific execution belongs in adapters and `registry/providers`, not
in global startup files.
