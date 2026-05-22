import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import { LocationProvider } from "./context/LocationContext";
import { Layout } from "./components/Layout";
import { Toaster } from "./components/ui/sonner";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";

// Pages
import HomePage from "./pages/HomePage";
import EventsPage from "./pages/EventsPage";
import EventDetailPage from "./pages/EventDetailPage";
import FoodTrucksPage from "./pages/FoodTrucksPage";
import RestaurantsPage from "./pages/RestaurantsPage";
import RestaurantDetailPage from "./pages/RestaurantDetailPage";
import AttractionsPage from "./pages/AttractionsPage";
import AttractionDetailPage from "./pages/AttractionDetailPage";
import ChurchesPage from "./pages/ChurchesPage";
import ChurchDetailPage from "./pages/ChurchDetailPage";
import CommunityPage from "./pages/CommunityPage";
import CreateEventPage from "./pages/CreateEventPage";
import DashboardPage from "./pages/DashboardPage";
import TicketSuccessPage from "./pages/TicketSuccessPage";
import PricingPage from "./pages/PricingPage";
import FlashDealsPage from "./pages/FlashDealsPage";
import LoginPage, { AuthCallback } from "./pages/AuthPages";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import PrivacyPage from "./pages/PrivacyPage";
import TermsPage from "./pages/TermsPage";
import AboutPage from "./pages/AboutPage";
import SearchResultsPage from "./pages/SearchResultsPage";
import AdminDigestPage from "./pages/AdminDigestPage";
import AdminReportsPage from "./pages/AdminReportsPage";
import AdminCommunitySourcesPage from "./pages/AdminCommunitySourcesPage";
import AdminRedditPostPage from "./pages/AdminRedditPostPage";
import CommunitySourcesPage from "./pages/CommunitySourcesPage";
import CommunitySourceSubmitPage from "./pages/CommunitySourceSubmitPage";
import UnsubscribePage from "./pages/UnsubscribePage";
import NotFoundPage from "./pages/NotFoundPage";

// App Router
function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        path="/*"
        element={
          <Layout>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/events" element={<EventsPage />} />
              <Route path="/events/:eventId" element={<EventDetailPage />} />
              <Route path="/food-trucks" element={<FoodTrucksPage />} />
              <Route path="/restaurants" element={<RestaurantsPage />} />
              <Route path="/restaurants/:restaurantId" element={<RestaurantDetailPage />} />
              <Route path="/attractions" element={<AttractionsPage category="outdoor" />} />
              <Route path="/attractions/:attractionId" element={<AttractionDetailPage />} />
              <Route path="/fitness" element={<AttractionsPage category="fitness" />} />
              <Route path="/fitness/:attractionId" element={<AttractionDetailPage />} />
              <Route path="/activities" element={<AttractionsPage category="activities" />} />
              <Route path="/activities/:attractionId" element={<AttractionDetailPage />} />
              <Route path="/churches" element={<ChurchesPage />} />
              <Route path="/churches/:churchId" element={<ChurchDetailPage />} />
              <Route path="/community" element={<CommunityPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/flash-deals" element={<FlashDealsPage />} />
              <Route path="/create-event" element={<CreateEventPage />} />
              <Route path="/events/:eventId/edit" element={<CreateEventPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/my-events" element={<DashboardPage />} />
              <Route path="/my-tickets" element={<DashboardPage />} />
              <Route path="/tickets/success" element={<TicketSuccessPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/terms" element={<TermsPage />} />
              <Route path="/about" element={<AboutPage />} />
              <Route path="/search" element={<SearchResultsPage />} />
              <Route path="/admin/digest" element={<AdminDigestPage />} />
              <Route path="/admin/reports" element={<AdminReportsPage />} />
              <Route path="/admin/community-sources" element={<AdminCommunitySourcesPage />} />
              <Route path="/admin/reddit" element={<AdminRedditPostPage />} />
              <Route path="/community-sources" element={<CommunitySourcesPage />} />
              <Route path="/community-sources/submit" element={<CommunitySourceSubmitPage />} />
              <Route path="/unsubscribe" element={<UnsubscribePage />} />
              {/* Catch-all 404 — must stay last inside the inner Routes */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Layout>
        }
      />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <LocationProvider>
              <AppRouter />
              <Toaster position="top-right" richColors />
              <Analytics />
              <SpeedInsights />
            </LocationProvider>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </div>
  );
}

export default App;
