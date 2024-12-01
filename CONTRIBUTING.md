# Contribution Guide

Thank you for your interest in the Sunscan project! This document will guide you through the necessary steps to contribute effectively.

## How to Contribute

### 1. Reporting a Bug

- First, check if the bug has already been reported by reviewing the [existing issues](https://github.com/staros-projects/sunscan-backend/issues).
- If the bug has not been reported, open a new issue and provide as much detail as possible:
  - A clear and concise description of the problem.
  - Steps to reproduce the bug.
  - The version of Python and the project you are using.
  - Any relevant error messages.

### 2. Proposing an Enhancement

- Check the existing issues to see if your idea has already been proposed.
- Open a new issue to discuss your idea before starting to work on it.
- Provide a detailed description of the proposed enhancement.

#### Main Branch Policy

The `main` branch is reserved exclusively for the production-ready version of Sunscan OS.

### 3. Adding New Features

- All major new features must be developed on a dedicated branch, named according to the feature (e.g., `feat-xxxx`).
- Submit your contribution as a **pull request (PR)** for integration into the main branch after passing the required tests.

### 4. Experimental Development

- Major independant changes to the **Sunscan backend** or critical components (e.g., testing a new Raspberry Pi model, operating system, or battery) are considered **experimental**.
- Such contributions must be submitted as PRs on a dedicated branch named `experimental-xxxx` (e.g., `experimental-battery`).
- These developments require thorough testing before integrating them into the core components of the project.

---

## Current Technical Specifications

Sunscan is currently based on the following:

- **Operating System**: Raspbian OS
- **Recommended Hardware**: Raspberry Pi 4B (8 GB) — core developments are validated on this board.
  - Any other hardware must be thoroughly tested across the entire system (backend, frontend, hardware), and the documentation must be updated accordingly.
- **Battery**: PiSugar 3 Plus Portable.
  - For more details, visit [www.sunscan.net](https://www.sunscan.net).

## Submitting a Pull Request

1. **Fork** the repository and clone your fork locally.
2. Create a branch for your contribution:
   ```bash
   git checkout -b your-branch-name
   ```
3. Make your changes and ensure the code is well-documented.
4. Test your changes locally.
5. Commit your changes with a clear message:
   ```bash
   git commit -m "Description of your change"
   ```
6. Push your branch to your fork:
   ```bash
    git push origin your-branch-name
   ```
7. Open a pull request to the main branch of the project.

## Code Style

- Follow PEP 8 style guidelines for Python code.
- Use docstrings to document functions and classes.
- Ensure the code is readable and well-commented.

## Tests

- Add tests for all new features and bug fixes.
- Use `pytest` to run the tests.
- Ensure all tests pass before submitting your pull request.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Help Channels

If you have questions or need support, you can:

Open a discussion on [GitHub Discussions](https://github.com/staros-projects/sunscan-backend/discussions)
Contact the maintainers directly via the contact form on [www.sunscan.net](www.sunscan.net).

## Resources

- [Project Documentation](https://github.com/staros-projects/sunscan-backend/docs)
- [Guide to Getting Started with Git and GitHub](https://guides.github.com/)
- [PEP 8 Style Guide for Python Code](https://www.python.org/dev/peps/pep-0008/)
- [pytest Documentation](https://docs.pytest.org/en/6.2.x/)
- [Raspberry Pi Documentation](https://www.raspberrypi.org/documentation/)
- [PiSugar 3 Plus Portable Documentation](https://www.pisugar.com/)
- [Sunscan Website](https://www.sunscan.net)

Thank you again for your contribution!
