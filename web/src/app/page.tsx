import { LeafCornerAccent } from "@/components/ecology/LeafCornerAccent";
import { WelcomePage } from "@/components/auth/WelcomePage";

export default function Home() {
  return (
    <div className="relative min-h-full flex-1 overflow-x-hidden">
      <LeafCornerAccent />
      <WelcomePage />
    </div>
  );
}
