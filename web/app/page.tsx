import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <h1>Prometheus Strategy OS</h1>
      <p>
        This is a placeholder Next.js surface for the evidence-linked decision
        workspace. Wire up API calls to <code>/v1/pipeline/run</code> once the
        backend service is running.
      </p>
      <p>
        Documentation lives in <code>docs/</code>; start with the developer
        experience guide to understand the pipeline contracts.
      </p>
      <p>
        Ready to explore?{" "}
        <Link href="https://localhost:8000/docs">Launch the API</Link>
      </p>
    </main>
  );
}
