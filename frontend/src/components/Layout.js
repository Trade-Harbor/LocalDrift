import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useLocation as useLocationContext } from '../context/LocationContext';
import { Button } from '../components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';
import {
  MapPin,
  Sun,
  Moon,
  Menu,
  X,
  User,
  LogOut,
  Calendar,
  Ticket,
  LayoutDashboard,
  Truck,
  Plus,
  Instagram,
  Facebook
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { FeedbackButton } from './FeedbackButton';

// Beta banner — small dismissable strip at the top of every page reminding
// visitors LocalDrift is in beta. Dismissal is sticky via localStorage so
// repeat visitors don't see it again.
const BETA_BANNER_KEY = 'localdrift_beta_banner_dismissed';

const BetaBanner = () => {
  const [dismissed, setDismissed] = useState(true);  // start true to avoid SSR flash
  useEffect(() => {
    setDismissed(localStorage.getItem(BETA_BANNER_KEY) === '1');
  }, []);

  if (dismissed) return null;
  return (
    <div className="bg-gradient-to-r from-indigo-500 to-pink-500 text-white text-sm">
      <div className="container mx-auto max-w-7xl px-4 py-2 flex items-center justify-between gap-3">
        <p>
          🎉 <strong>LocalDrift is in beta.</strong> Everything's free — found something off?
          Tap <strong>Send Feedback</strong> in the corner.
        </p>
        <button
          onClick={() => {
            localStorage.setItem(BETA_BANNER_KEY, '1');
            setDismissed(true);
          }}
          aria-label="Dismiss banner"
          className="p-1 hover:bg-white/20 rounded-full transition-colors flex-shrink-0"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

export const Navbar = () => {
  const { user, logout, isAuthenticated } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { location } = useLocationContext();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/60" data-testid="navbar">
      <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl">
        <div className="flex h-16 items-center justify-between">
          {/* Logo. pr-4 on the wordmark gives extra visual separation
              from the first nav link — the gradient text can otherwise
              read as bleeding into the adjacent "Events" link because
              of the color contrast against the dark navbar. */}
          <Link to="/" className="flex items-center space-x-2 shrink-0" data-testid="logo-link">
            <img
              src="/logo-icon.png"
              alt="LocalDrift"
              className="h-10 w-10 object-contain"
              loading="eager"
            />
            <span className="font-heading font-bold text-xl gradient-brand-text hidden sm:block pr-4">LocalDrift</span>
          </Link>

          {/* Desktop Navigation — show only at xl+ (1280px). Nine links
              plus location indicator, theme toggle, and auth buttons
              don't fit cleanly below that — "Food Trucks" wraps and
              everything else gets shoved sideways. Below xl we use the
              hamburger menu (mobile drawer), which already scales well.
              whitespace-nowrap prevents "Food Trucks" from breaking
              even if a future tweak pinches widths. */}
          <div className="hidden xl:flex items-center gap-x-5 mx-6 whitespace-nowrap">
            <Link 
              to="/events" 
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-events"
            >
              Events
            </Link>
            <Link 
              to="/restaurants" 
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-restaurants"
            >
              Restaurants
            </Link>
            <Link
              to="/attractions"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-attractions"
            >
              Explore
            </Link>
            <Link
              to="/fitness"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-fitness"
            >
              Fitness
            </Link>
            <Link
              to="/activities"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-activities"
            >
              Activities
            </Link>
            <Link
              to="/food-trucks"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-food-trucks"
            >
              Food Trucks
            </Link>
            <Link
              to="/churches"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-churches"
            >
              Churches
            </Link>
            <Link
              to="/community"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-community"
            >
              Community
            </Link>
            <Link
              to="/community-sources"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-community-sources"
            >
              Local Voices
            </Link>
            <Link
              to="/pricing"
              className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              data-testid="nav-pricing"
            >
              Pricing
            </Link>
          </div>

          {/* Right Side */}
          <div className="flex items-center space-x-3">
            {/* Location Indicator */}
            <button 
              className="hidden sm:flex items-center space-x-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => navigate('/events')}
              data-testid="location-indicator"
            >
              <MapPin className="h-4 w-4" />
              <span className="max-w-[120px] truncate">{location?.city || 'Set Location'}</span>
            </button>

            {/* Theme Toggle */}
            <Button 
              variant="ghost" 
              size="icon" 
              onClick={toggleTheme}
              className="rounded-full"
              data-testid="theme-toggle"
            >
              {theme === 'dark' ? (
                <Sun className="h-5 w-5" />
              ) : (
                <Moon className="h-5 w-5" />
              )}
            </Button>

            {/* Auth Section */}
            {isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="relative h-9 w-9 rounded-full" data-testid="user-menu-trigger">
                    <Avatar className="h-9 w-9">
                      <AvatarImage src={user?.profile_picture} alt={user?.name} />
                      <AvatarFallback className="bg-primary text-primary-foreground">
                        {user?.name?.charAt(0)?.toUpperCase() || 'U'}
                      </AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-56" align="end" forceMount>
                  <div className="flex items-center justify-start gap-2 p-2">
                    <div className="flex flex-col space-y-1">
                      <p className="text-sm font-medium">{user?.name}</p>
                      <p className="text-xs text-muted-foreground">{user?.email}</p>
                    </div>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate('/dashboard')} data-testid="menu-dashboard">
                    <LayoutDashboard className="mr-2 h-4 w-4" />
                    Dashboard
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate('/my-events')} data-testid="menu-my-events">
                    <Calendar className="mr-2 h-4 w-4" />
                    My Events
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate('/my-tickets')} data-testid="menu-my-tickets">
                    <Ticket className="mr-2 h-4 w-4" />
                    My Tickets
                  </DropdownMenuItem>
                  {user?.account_type === 'business' && (
                    <DropdownMenuItem onClick={() => navigate('/my-food-trucks')} data-testid="menu-my-trucks">
                      <Truck className="mr-2 h-4 w-4" />
                      My Food Trucks
                    </DropdownMenuItem>
                  )}
                  {/* Create Event hidden during beta until the user-submission
                      flow is fully tested. Route /create-event still works
                      for direct-URL testing. */}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} data-testid="menu-logout">
                    <LogOut className="mr-2 h-4 w-4" />
                    Log out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <div className="flex items-center space-x-2">
                <Button 
                  variant="ghost" 
                  onClick={() => navigate('/login')}
                  className="hidden sm:inline-flex"
                  data-testid="login-btn"
                >
                  Sign In
                </Button>
                <Button 
                  onClick={() => navigate('/register')}
                  className="rounded-full bg-gradient-to-r from-indigo-500 to-pink-500 hover:opacity-90"
                  data-testid="register-btn"
                >
                  Get Started
                </Button>
              </div>
            )}

            {/* Mobile Menu Toggle — visible below xl (matches the
                desktop nav's hidden-until-xl breakpoint) */}
            <Button
              variant="ghost"
              size="icon"
              className="xl:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              data-testid="mobile-menu-toggle"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>
        </div>

        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="xl:hidden border-t border-border py-4 animate-slide-up" data-testid="mobile-menu">
            <div className="flex flex-col space-y-3">
              <Link 
                to="/events" 
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Events
              </Link>
              <Link 
                to="/restaurants" 
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Restaurants
              </Link>
              <Link
                to="/attractions"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Explore
              </Link>
              <Link
                to="/fitness"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Fitness
              </Link>
              <Link
                to="/activities"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Activities
              </Link>
              <Link
                to="/food-trucks"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Food Trucks
              </Link>
              <Link
                to="/churches"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Churches
              </Link>
              <Link
                to="/community"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Community
              </Link>
              <Link
                to="/community-sources"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Local Voices
              </Link>
              <Link
                to="/pricing"
                className="px-2 py-2 text-sm font-medium hover:bg-muted rounded-lg transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Pricing
              </Link>
              {/* "Post Event" mobile link hidden during beta — see comment
                  in dropdown menu above. */}
              <div className="flex items-center space-x-1 px-2 py-2 text-sm text-muted-foreground">
                <MapPin className="h-4 w-4" />
                <span>{location?.city || 'Set Location'}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};

export const Footer = () => {
  return (
    <footer className="border-t border-border bg-muted/30 mt-auto" data-testid="footer">
      <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="col-span-2 md:col-span-1">
            <Link to="/" className="flex items-center space-x-2 mb-4">
              <img
                src="/logo-icon.png"
                alt="LocalDrift"
                className="h-9 w-9 object-contain"
                loading="lazy"
              />
              <span className="font-heading font-bold text-lg">LocalDrift</span>
            </Link>
            <p className="text-sm text-muted-foreground mb-4">
              Discover what's happening in your community. Events, food trucks, and local experiences.
            </p>
            {/* Social links. Lives in the brand column so the visual
                identity (logo, name, tagline, socials) groups together.
                Icons sized to match the body text rhythm; hover lifts
                from muted-foreground to primary for the standard
                "this is interactive" affordance. */}
            <div className="flex items-center gap-3" aria-label="LocalDrift on social media">
              <a
                href="https://www.instagram.com/localdrift.app/"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="LocalDrift on Instagram"
                className="text-muted-foreground hover:text-primary transition-colors"
                data-testid="footer-instagram"
              >
                <Instagram className="h-5 w-5" />
              </a>
              <a
                href="https://www.facebook.com/profile.php?id=61590000928752"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="LocalDrift on Facebook"
                className="text-muted-foreground hover:text-primary transition-colors"
                data-testid="footer-facebook"
              >
                <Facebook className="h-5 w-5" />
              </a>
            </div>
          </div>
          
          <div>
            <h4 className="font-heading font-semibold mb-4">Explore</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link to="/events" className="hover:text-foreground transition-colors">All Events</Link></li>
              <li><Link to="/restaurants" className="hover:text-foreground transition-colors">Restaurants</Link></li>
              <li><Link to="/food-trucks" className="hover:text-foreground transition-colors">Food Trucks</Link></li>
              <li><Link to="/attractions" className="hover:text-foreground transition-colors">Explore</Link></li>
              <li><Link to="/fitness" className="hover:text-foreground transition-colors">Fitness</Link></li>
              <li><Link to="/activities" className="hover:text-foreground transition-colors">Activities</Link></li>
              <li><Link to="/churches" className="hover:text-foreground transition-colors">Churches</Link></li>
            </ul>
          </div>
          
          <div>
            <h4 className="font-heading font-semibold mb-4">For Business</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link to="/register?type=business" className="hover:text-foreground transition-colors">Business Account</Link></li>
              <li><Link to="/pricing" className="hover:text-foreground transition-colors">Pricing</Link></li>
              <li><a href="mailto:business@localdrift.app" className="hover:text-foreground transition-colors">Partner with us</a></li>
            </ul>
          </div>
          
          <div>
            <h4 className="font-heading font-semibold mb-4">Support</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link to="/about" className="hover:text-foreground transition-colors">About</Link></li>
              <li><a href="mailto:hello@localdrift.app" className="hover:text-foreground transition-colors">Contact</a></li>
              <li><Link to="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link></li>
              <li><Link to="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link></li>
            </ul>
          </div>
        </div>

        {/* Data attributions — required by partner ToS */}
        <div className="border-t border-border mt-8 pt-6 text-xs text-muted-foreground">
          <p className="mb-2">
            Restaurant and food-truck data <strong>powered by Yelp</strong>.
            Map and attraction data <strong>© OpenStreetMap contributors</strong>.
            Concert and sports event data via Ticketmaster Discovery API and SeatGeek.
            Local news headlines via Google News.
          </p>
        </div>

        <div className="border-t border-border mt-6 pt-6 flex flex-col md:flex-row justify-between items-center">
          <p className="text-sm text-muted-foreground">
            © {new Date().getFullYear()} LocalDrift · Beta
          </p>
          <p className="text-sm text-muted-foreground mt-2 md:mt-0">
            Made for local communities · Wilmington, NC
          </p>
        </div>
      </div>
    </footer>
  );
};

export const Layout = ({ children }) => {
  return (
    <div className="min-h-screen flex flex-col">
      <BetaBanner />
      <Navbar />
      <main className="flex-1">{children}</main>
      <Footer />
      <FeedbackButton />
    </div>
  );
};
