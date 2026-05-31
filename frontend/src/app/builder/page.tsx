import nextDynamic from "next/dynamic";

// ReactFlow accesses browser APIs at module load time — importing it on the
// server crashes the SSR pre-render silently, producing a 404 HTML.
// Dynamic import with ssr:false keeps ALL ReactFlow code off the server entirely.
const BuilderClient = nextDynamic(() => import("./_client"), {
  ssr: false,
  loading: () => <div className="fixed inset-0 bg-cream" />,
});

export default function BuilderPage() {
  return <BuilderClient />;
}
