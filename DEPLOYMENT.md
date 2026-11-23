# Static demo deployment

PauseCheck is a static HTML/CSS/JavaScript app. It has no server-side message processing, API keys, build step, analytics, or paid service requirement. Relative app and service-worker paths support a GitHub Pages project site under `/pausecheck-slays-hacks/`.

A GitHub Actions workflow is provided at `.github/workflows/pages.yml`. It uploads the repository root as the site and deploys when code is pushed to `main`, or when manually dispatched. Before the first deployment, enable GitHub Pages for the repository and choose **GitHub Actions** as the publishing source, following [GitHub’s custom-workflow instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages). A public push to `main` will make the static site available to anyone and trigger deployment.

To check locally before release, run `python3 -m http.server 8000 --bind 127.0.0.1` from the project folder, then open `http://127.0.0.1:8000/`. The app needs a local HTTP server or HTTPS because it uses a service worker; direct `file://` opening is unsupported.
