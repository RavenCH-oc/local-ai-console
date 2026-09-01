export function PersonalPage() {
  return (
    <section className="page" aria-labelledby="personal-heading">
      <p className="eyebrow">Planned workspace</p>
      <h1 id="personal-heading">Personal Chat</h1>
      <p className="page-lead">Planned. This foundation intentionally does not include a chat interface.</p>
      <ul className="planned-list">
        <li>Conversations</li>
        <li>Generation settings</li>
        <li>Context management</li>
      </ul>
    </section>
  );
}
