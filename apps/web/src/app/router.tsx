import { Route, Routes } from "react-router-dom";

import { AppShell } from "../components/AppShell/AppShell";
import { DiscordBotPage } from "../pages/DiscordBotPage";
import { HomePage } from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PersonalPage } from "../pages/PersonalPage";
import { PromptWorkbenchPage } from "../pages/PromptWorkbenchPage";
import { SettingsPage } from "../pages/SettingsPage";
import { WaifuBotPage } from "../pages/WaifuBotPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/personal" element={<PersonalPage />} />
        <Route path="/tools/prompt-workbench" element={<PromptWorkbenchPage />} />
        <Route path="/services/discord" element={<DiscordBotPage />} />
        <Route path="/services/waifu" element={<WaifuBotPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
