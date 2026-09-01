import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <section className="page" aria-labelledby="not-found-heading">
      <p className="eyebrow">Route not found</p>
      <h1 id="not-found-heading">This workspace does not exist</h1>
      <p className="page-lead">Use the application navigation to return to an available foundation page.</p>
      <Link className="primary-link" to="/">
        Go to Home
      </Link>
    </section>
  );
}
