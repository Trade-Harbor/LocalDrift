import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import {
  Search, Megaphone, ExternalLink, Plus, X,
  MessageSquare, Users, Facebook, Instagram, Youtube, BookOpen, Mail, Mic, Radio,
} from 'lucide-react';
import ReportButton from '../components/ReportButton';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Category metadata — icon + label + accent color for the card chip.
// Stays in sync with the backend's COMMUNITY_SOURCE_CATEGORIES set.
const CATEGORIES = [
  { value: 'subreddit',       label: 'Subreddit',         icon: MessageSquare, color: 'from-orange-500 to-red-500' },
  { value: 'facebook_group',  label: 'Facebook group',    icon: Users,         color: 'from-blue-500 to-indigo-500' },
  { value: 'facebook_page',   label: 'Facebook page',     icon: Facebook,      color: 'from-blue-600 to-indigo-600' },
  { value: 'instagram',       label: 'Instagram',         icon: Instagram,     color: 'from-pink-500 to-purple-500' },
  { value: 'tiktok',          label: 'TikTok',            icon: Radio,         color: 'from-zinc-500 to-zinc-700' },
  { value: 'youtube',         label: 'YouTube',           icon: Youtube,       color: 'from-red-500 to-rose-500' },
  { value: 'blog',            label: 'Blog',              icon: BookOpen,      color: 'from-emerald-500 to-teal-500' },
  { value: 'newsletter',      label: 'Newsletter',        icon: Mail,          color: 'from-amber-500 to-orange-500' },
  { value: 'podcast',         label: 'Podcast',           icon: Mic,           color: 'from-violet-500 to-purple-500' },
  { value: 'other',           label: 'Other',             icon: Radio,         color: 'from-slate-500 to-slate-600' },
];

const CATEGORY_BY_VALUE = Object.fromEntries(CATEGORIES.map((c) => [c.value, c]));

export default function CommunitySourcesPage() {
  usePageTitle('Local Voices');

  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [category, setCategory] = useState('all');

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (category && category !== 'all') params.category = category;
      if (searchQuery.trim()) params.q = searchQuery.trim();
      const res = await axios.get(`${API_URL}/api/community-sources`, { params });
      setSources(res.data.items || []);
    } catch (err) {
      console.error('Error fetching community sources:', err);
    } finally {
      setLoading(false);
    }
  }, [category, searchQuery]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchSources();
  };

  const clearFilters = () => {
    setSearchQuery('');
    setCategory('all');
  };

  return (
    <div className="min-h-screen bg-background" data-testid="community-sources-page">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-12">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-3 bg-white/20 rounded-xl backdrop-blur-sm">
              <Megaphone className="h-6 w-6" />
            </div>
            <h1 className="font-heading text-3xl md:text-4xl font-bold">Local Voices</h1>
          </div>
          <p className="text-white/80 max-w-2xl">
            The people, pages, and subreddits keeping Wilmington informed.
            Follow them on their own platforms — LocalDrift just helps you find them.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="sticky top-16 z-40 bg-background/95 backdrop-blur-sm border-b border-border">
        <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-4">
          <div className="flex flex-wrap items-center gap-3">
            <form onSubmit={handleSearch} className="flex-1 min-w-[200px] max-w-md">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search by name, description, or topic..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 rounded-full"
                  data-testid="community-sources-search"
                />
              </div>
            </form>

            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="w-[180px] rounded-full">
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORIES.map((c) => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {(category !== 'all' || searchQuery) && (
              <Button variant="ghost" onClick={clearFilters} className="text-muted-foreground">
                <X className="h-4 w-4 mr-1" /> Clear
              </Button>
            )}

            <Button asChild className="rounded-full ml-auto">
              <Link to="/community-sources/submit" data-testid="submit-source-cta">
                <Plus className="h-4 w-4 mr-1" /> Submit yours
              </Link>
            </Button>
          </div>

          <div className="mt-3 text-sm text-muted-foreground">
            {sources.length} {sources.length === 1 ? 'source' : 'sources'} in the directory
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-7xl py-8">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-56 bg-muted rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : sources.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {sources.map((s) => (
              <SourceCard key={s.source_id} source={s} />
            ))}
          </div>
        ) : (
          <EmptyState onClear={clearFilters} hasFilters={category !== 'all' || !!searchQuery} />
        )}
      </div>
    </div>
  );
}

function SourceCard({ source }) {
  const cat = CATEGORY_BY_VALUE[source.category] || CATEGORY_BY_VALUE.other;
  const Icon = cat.icon;

  return (
    <Card
      className="group overflow-hidden border-0 shadow-card hover:shadow-card-hover transition-all duration-300 hover:-translate-y-1 dark:border dark:border-white/10"
      data-testid={`source-card-${source.source_id}`}
    >
      <CardContent className="p-5">
        {/* Header row: icon + name + report */}
        <div className="flex items-start gap-3 mb-3">
          <div className={`p-2.5 rounded-xl bg-gradient-to-br ${cat.color} text-white flex-shrink-0`}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-heading font-semibold text-lg leading-tight line-clamp-2 group-hover:text-primary transition-colors">
              {source.name}
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">{cat.label}</p>
          </div>
          <ReportButton targetType="creator" targetId={source.source_id} />
        </div>

        {/* Description */}
        {source.description && (
          <p className="text-sm text-muted-foreground mb-3 line-clamp-3">
            {source.description}
          </p>
        )}

        {/* Coverage tags */}
        {source.coverage_tags?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {source.coverage_tags.slice(0, 5).map((tag, idx) => (
              <Badge key={idx} variant="secondary" className="text-xs capitalize">
                #{tag}
              </Badge>
            ))}
          </div>
        )}

        {/* Platform link buttons */}
        <div className="flex flex-wrap gap-2 mt-3">
          {source.links?.map((lnk, idx) => (
            <Button
              key={idx}
              variant="outline"
              size="sm"
              className="rounded-full text-xs h-8"
              asChild
            >
              <a
                href={ensureScheme(lnk.url)}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`source-link-${source.source_id}-${idx}`}
              >
                <ExternalLink className="h-3 w-3 mr-1" />
                {lnk.handle || lnk.platform || 'Visit'}
              </a>
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({ onClear, hasFilters }) {
  return (
    <div className="text-center py-16">
      <Megaphone className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
      <h3 className="text-xl font-semibold mb-2">
        {hasFilters ? 'No matches' : 'No local voices yet'}
      </h3>
      <p className="text-muted-foreground mb-6 max-w-md mx-auto">
        {hasFilters
          ? 'Try clearing your filters, or be the first to add a creator that matches.'
          : 'Run a local subreddit, blog, podcast, or community page? Submit it and we\'ll review it within a few days.'}
      </p>
      <div className="flex flex-col sm:flex-row gap-2 justify-center">
        {hasFilters && (
          <Button variant="outline" onClick={onClear} className="rounded-full">
            <X className="h-4 w-4 mr-1" /> Clear filters
          </Button>
        )}
        <Button asChild className="rounded-full">
          <Link to="/community-sources/submit">
            <Plus className="h-4 w-4 mr-1" /> Submit a source
          </Link>
        </Button>
      </div>
    </div>
  );
}

// Add https:// scheme if the submitted URL was bare (e.g. "reddit.com/r/x").
// Backend validation just requires a "." — we're more lenient than strict
// URL parsing — so we patch the scheme client-side before opening.
function ensureScheme(url) {
  const trimmed = (url || '').trim();
  if (!trimmed) return '#';
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}
