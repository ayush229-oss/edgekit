import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-paper px-6 py-12">
      <div className="mb-8 text-center">
        <div className="inline-flex items-center gap-2 mb-3">
          <div className="w-8 h-8 rounded-md bg-ink flex items-center justify-center text-paper font-bold text-sm">
            E
          </div>
          <span className="font-semibold tracking-tight text-[17px] text-ink">Edgekit</span>
        </div>
        <h1 className="text-[24px] font-bold tracking-tight text-ink">Create your account</h1>
        <p className="text-[13px] text-muted mt-1.5">Free forever. No credit card.</p>
      </div>

      <SignUp
        signInUrl="/sign-in"
        forceRedirectUrl="/onboarding"
        appearance={{
          elements: {
            rootBox:         "w-full max-w-md",
            card:            "shadow-soft border border-border rounded-2xl bg-surface",
            headerTitle:     "hidden",
            headerSubtitle:  "hidden",
            socialButtonsBlockButton: "border border-border hover:bg-surface2 transition-colors rounded-lg",
            formButtonPrimary: "bg-money hover:bg-moneyDark text-white rounded-lg normal-case font-medium",
            footerActionLink: "text-money hover:text-moneyDark",
            formFieldInput:  "rounded-lg border-border focus:ring-money",
          },
          variables: {
            colorPrimary:    "#0B6E4F",
            colorBackground: "#FFFFFF",
            colorText:       "#0A0A0A",
            colorTextSecondary: "#86868B",
            borderRadius:    "10px",
            fontFamily:      "Inter, system-ui, sans-serif",
          },
        }}
      />

      <p className="text-[11px] text-muted mt-6 text-center max-w-md">
        By creating an account you agree to use Edgekit for research only.
        Not investment advice. We never trade on your behalf.
      </p>
    </div>
  );
}
