// Legacy route — CSV upload is now in Resources → Data source.
import { redirect } from "next/navigation";
export default function UploadPage() { redirect("/resources"); }
