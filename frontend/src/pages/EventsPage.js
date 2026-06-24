import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Slider } from '../components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { EventCard } from '../components/Cards';
import { EventMap } from '../components/Maps';
import { useLocation as useLocationContext } from '../context/LocationContext';
import { format } from 'date-fns';
import { 
  Search, 
  Filter, 
  MapPin, 
  CalendarIcon, 
  Grid3X3, 
  Map as MapIcon,
  X,
  SlidersHorizontal
} from 'lucide-react';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const CATEGORIES = [
  { value: 'all', label: 'All Categories' },
  { value: 'concert', label: 'Concerts' },
  { value: 'theater', label: 'Theater' },
  { value: 'comedy', label: 'Comedy' },
  { value: 'parade', label: 'Parades' },
  { value: 'marathon', label: 'Marathons' },
  { value: 'market', label: 'Markets' },
  { value: 'happy_hour', label: 'Happy Hours' },
  { value: 'garage_sale', label: 'Garage Sales' },
  { value: 'food_festival', label: 'Food Festivals' },
  { value: 'community', label: 'Community' },
  { value: 'sports', label: 'Sports' },
  { value: 'other', label: 'Other' },
];

export default function EventsPage() {
  usePageTitle('Events');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { location, radius, updateRadius } = useLocationContext();
  
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [viewMode, setViewMode] = useState('grid'); // grid or map
  const [showFilters, setShowFilters] = useState(false);

  const PAGE_SIZE = 50;
  
  // Filter states
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [selectedCategory, setSelectedCategory] = useState(searchParams.get('category') || 'all');
  const [selectedDate, setSelectedDate] = useState(null);
  const [freeOnly, setFreeOnly] = useState(false);
  const [localRadius, setLocalRadius] = useState(radius);

  useEffect(() => {
    fetchEvents();
  }, [location, radius, selectedCategory, selectedDate, freeOnly]);

  useEffect(() => {
    const categoryParam = searchParams.get('category');
    const searchParam = searchParams.get('search');
    if (categoryParam) setSelectedCategory(categoryParam);
    if (searchParam) setSearchQuery(searchParam);
  }, [searchParams]);

  const buildParams = (offset = 0, limit = PAGE_SIZE) => {
    const params = {
      latitude: location?.latitude,
      longitude: location?.longitude,
      radius,
      limit,
      offset,
    };
    if (selectedCategory && selectedCategory !== 'all') params.category = selectedCategory;
    if (searchQuery) params.search = searchQuery;
    if (selectedDate) params.start_date = format(selectedDate, 'yyyy-MM-dd');
    if (freeOnly) params.is_free = true;
    return params;
  };

  const fetchEvents = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_URL}/api/events`, { params: buildParams(0) });
      setEvents(response.data);
      // If we got fewer than a full page back, there's nothing more to load.
      setHasMore(response.data.length === PAGE_SIZE);
    } catch (error) {
      console.error('Error fetching events:', error);
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  };

  const loadMore = async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const response = await axios.get(`${API_URL}/api/events`, {
        params: buildParams(events.length),
      });
      if (response.data.length === 0) {
        setHasMore(false);
      } else {
        // Defensive: backend may rarely return overlapping rows if data
        // changed mid-scroll. Dedupe by event_id when appending.
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.event_id));
          const fresh = response.data.filter((e) => !seen.has(e.event_id));
          return [...prev, ...fresh];
        });
        setHasMore(response.data.length === PAGE_SIZE);
      }
    } catch (error) {
      console.error('Error loading more events:', error);
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchEvents();
  };

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedCategory('all');
    setSelectedDate(null);
    setFreeOnly(false);
    setLocalRadius(25);
    updateRadius(25);
    setSearchParams({});
  };

  const applyRadius = () => {
    updateRadius(localRadius);
  };

  const hasActiveFilters = searchQuery || selectedCategory !== 'all' || selectedDate || freeOnly || radius !== 25;

  return (
    <div className="min-h-screen bg-background" data-testid="events-page">
      {/* Header */}
      <div className="bg-muted/30 border-b border-border">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-8">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="font-heading text-3xl md:text-4xl font-bold">Discover Events</h1>
              <p className="text-muted-foreground mt-1">
                {events.length} events found within {radius} miles
              </p>
            </div>
            
            <div className="flex items-center gap-2">
              <Button
                variant={viewMode === 'grid' ? 'default' : 'outline'}
                size="icon"
                onClick={() => setViewMode('grid')}
                className="rounded-full"
                data-testid="view-grid-btn"
              >
                <Grid3X3 className="h-4 w-4" />
              </Button>
              <Button
                variant={viewMode === 'map' ? 'default' : 'outline'}
                size="icon"
                onClick={() => setViewMode('map')}
                className="rounded-full"
                data-testid="view-map-btn"
              >
                <MapIcon className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="sticky top-16 z-40 bg-background/95 backdrop-blur-sm border-b border-border">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search */}
            <form onSubmit={handleSearch} className="flex-1 min-w-[200px] max-w-md">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search events..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 rounded-full"
                  data-testid="search-input"
                />
              </div>
            </form>

            {/* Category Select */}
            <Select value={selectedCategory} onValueChange={setSelectedCategory}>
              <SelectTrigger className="w-[160px] rounded-full" data-testid="category-select">
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                {CATEGORIES.map((cat) => (
                  <SelectItem key={cat.value} value={cat.value}>
                    {cat.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* Date Picker */}
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" className="rounded-full gap-2" data-testid="date-picker-trigger">
                  <CalendarIcon className="h-4 w-4" />
                  {selectedDate ? format(selectedDate, 'MMM d') : 'Any Date'}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={selectedDate}
                  onSelect={setSelectedDate}
                  initialFocus
                />
              </PopoverContent>
            </Popover>

            {/* Free Only Toggle */}
            <Button
              variant={freeOnly ? 'default' : 'outline'}
              onClick={() => setFreeOnly(!freeOnly)}
              className="rounded-full"
              data-testid="free-only-btn"
            >
              Free Events
            </Button>

            {/* More Filters */}
            <Button
              variant="outline"
              onClick={() => setShowFilters(!showFilters)}
              className="rounded-full gap-2"
              data-testid="more-filters-btn"
            >
              <SlidersHorizontal className="h-4 w-4" />
              Distance
            </Button>

            {/* Clear Filters */}
            {hasActiveFilters && (
              <Button
                variant="ghost"
                onClick={clearFilters}
                className="text-muted-foreground"
                data-testid="clear-filters-btn"
              >
                <X className="h-4 w-4 mr-1" />
                Clear
              </Button>
            )}
          </div>

          {/* Distance Slider */}
          {showFilters && (
            <div className="mt-4 p-4 bg-muted/50 rounded-xl animate-slide-up">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Search Radius</span>
                <span className="text-sm text-muted-foreground">{localRadius} miles</span>
              </div>
              <div className="flex items-center gap-4">
                <Slider
                  value={[localRadius]}
                  onValueChange={([value]) => setLocalRadius(value)}
                  max={100}
                  min={5}
                  step={5}
                  className="flex-1"
                  data-testid="radius-slider"
                />
                <Button 
                  size="sm" 
                  onClick={applyRadius}
                  className="rounded-full"
                  data-testid="apply-radius-btn"
                >
                  Apply
                </Button>
              </div>
            </div>
          )}

          {/* Active Filters Display */}
          {hasActiveFilters && (
            <div className="flex flex-wrap gap-2 mt-3">
              {searchQuery && (
                <Badge variant="secondary" className="gap-1">
                  Search: {searchQuery}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setSearchQuery('')} />
                </Badge>
              )}
              {selectedCategory !== 'all' && (
                <Badge variant="secondary" className="gap-1">
                  {CATEGORIES.find(c => c.value === selectedCategory)?.label}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedCategory('all')} />
                </Badge>
              )}
              {selectedDate && (
                <Badge variant="secondary" className="gap-1">
                  {format(selectedDate, 'MMM d, yyyy')}
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setSelectedDate(null)} />
                </Badge>
              )}
              {freeOnly && (
                <Badge variant="secondary" className="gap-1">
                  Free Only
                  <X className="h-3 w-3 cursor-pointer" onClick={() => setFreeOnly(false)} />
                </Badge>
              )}
              {radius !== 25 && (
                <Badge variant="secondary" className="gap-1">
                  {radius} mile radius
                </Badge>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-8">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-80 bg-muted rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : viewMode === 'grid' ? (
          events.length > 0 ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {events.map((event) => (
                  <EventCard
                    key={event.event_id}
                    event={event}
                    onClick={() => navigate(`/events/${event.event_id}`)}
                  />
                ))}
              </div>
              <div className="mt-8 flex flex-col items-center gap-2" data-testid="events-load-more">
                {hasMore ? (
                  <Button
                    variant="outline"
                    size="lg"
                    className="rounded-full"
                    onClick={loadMore}
                    disabled={loadingMore}
                  >
                    {loadingMore ? 'Loading...' : 'Load more events'}
                  </Button>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    You've reached the end of the list ({events.length} events)
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="text-center py-16">
              <CalendarIcon className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-xl font-semibold mb-2">No events found</h3>
              <p className="text-muted-foreground mb-6">
                Try adjusting your filters or search radius
              </p>
              <Button onClick={clearFilters} className="rounded-full">
                Clear All Filters
              </Button>
            </div>
          )
        ) : (
          <div className="h-[600px] rounded-2xl overflow-hidden shadow-lg">
            <EventMap
              events={events}
              center={location ? [location.latitude, location.longitude] : [40.7128, -74.006]}
              zoom={11}
              onEventClick={(event) => navigate(`/events/${event.event_id}`)}
              showUserLocation={true}
              userLocation={location}
            />
          </div>
        )}
      </div>
    </div>
  );
}
