# Myrcat Developer Guidelines

## Setup & Commands
- Setup: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Run: `python myrcat.py` or `python myrcat.py -c /path/to/config.ini`
- Test: `./test/test.sh` (all tests) or `python ./test/lastfm.py` (Last.FM auth)

## Code Style Guidelines
- **Formatting**: 4-space indentation, ~88-100 char line length, PEP 8 compliant
- **Imports**: Standard library first, third-party next, local imports last, alphabetically sorted
- **Types**: Use type hints (`Optional[str]`, `Dict[str, Any]`), return types in signatures
- **Naming**: PascalCase for classes, snake_case for functions/variables, _leading_underscore for private
- **Strings**: Prefer f-strings for formatting
- **Documentation**: Triple double-quotes (`"""`) for docstrings
- **Error Handling**: Use try/except with appropriate logging, graceful recovery when possible
- **Logging**: Use built-in logging module with appropriate levels and descriptive emoji prefixes

## Code Organization
- Use dataclasses for structured data
- Modular design with clear separation of concerns
- Each class should have a single responsibility
- Use async/await for asynchronous operations