import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import Achievements from "@/pages/Achievements";
import Community from "@/pages/Community";
import FamilyWorkspace from "@/pages/FamilyWorkspace";
import Journey from "@/pages/Journey";
import Moments from "@/pages/Moments";
import Profile from "@/pages/Profile";
import Support from "@/pages/Support";
import Today from "@/pages/Today";
import Understand from "@/pages/Understand";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";


function Router() {
  return (
    <Switch>
      <Route path={"/"} component={Home} />
      <Route path={"/today"} component={Today} />
      <Route path={"/understand"} component={Understand} />
      <Route path={"/journey"} component={Journey} />
      <Route path={"/moments"} component={Moments} />
      <Route path={"/support"} component={Support} />
      <Route path={"/community"} component={Community} />
      <Route path={"/family"} component={FamilyWorkspace} />
      <Route path={"/achievements"} component={Achievements} />
      <Route path={"/profile"} component={Profile} />
      <Route path={"/404"} component={NotFound} />
      {/* Final fallback route */}
      <Route component={NotFound} />
    </Switch>
  );
}

// NOTE: About Theme
// - First choose a default theme according to your design style (dark or light bg), than change color palette in index.css
//   to keep consistent foreground/background color across components
// - If you want to make theme switchable, pass `switchable` ThemeProvider and use `useTheme` hook

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider
        defaultTheme="light"
      >
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
