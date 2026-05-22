import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '../components/ui/tabs';
import {
  Share2, Copy, Check, Loader2, RefreshCw, Calendar,
} from 'lucide-react';
import { toast } from 'sonner';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Admin: Reddit-bot dry-run preview UI.
 *
 * This is the tool we use to produce the community-vote post on
 * r/Wilmington. Loads all 3 style variants for the picked month in one
 * call, shows each in its own tab with rendered markdown + a copy
 * button. Side-by-side tab layout makes it easy to spot which one
 * reads best before pasting into a Reddit post draft.
 *
 * No live posting from this page yet — Phase F adds the Post button.
 * Auth: ?token=ADMIN_TOKEN in URL (same pattern as /admin/digest and
 * /admin/community-sources).
 */

const STYLES = [
  { value: 'weekly',        label: 'Weekly breakdown' },
  { value: 'by_category',   label: 'By category' },
  { value: 'chronological', label: 'Chronological' },
];

export default function AdminRedditPostPage() {
  usePageTitle('Admin · Reddit preview');
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  const [month, setMonth] = useState(defaultMonth());
  const [includeTickets, setIncludeTickets] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [copiedStyle, setCopiedStyle] = useState(null);

  const fetchPreviews = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/reddit/preview-all`, {
        params: { token, month, include_tickets: includeTickets },
      });
      setData(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load previews');
    } finally {
      setLoading(false);
    }
  }, [token, month, includeTickets]);

  useEffect(() => { fetchPreviews(); }, [fetchPreviews]);

  const copyMarkdown = async (styleKey, markdown) => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopiedStyle(styleKey);
      toast.success('Markdown copied — paste into Reddit');
      // Reset the copied indicator after a couple seconds
      setTimeout(() => setCopiedStyle((current) => (current === styleKey ? null : current)), 2000);
    } catch (err) {
      toast.error('Clipboard copy failed — long-press to copy manually');
    }
  };

  if (!token) {
    return (
      <div className="container mx-auto max-w-xl py-16 px-4">
        <h1 className="font-heading text-2xl font-bold mb-2">Admin · Reddit preview</h1>
        <p className="text-muted-foreground">
          Append <code>?token=YOUR_ADMIN_TOKEN</code> to the URL to access this page.
        </p>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-5xl py-8 px-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
            <Share2 className="h-6 w-6 text-primary" />
            Reddit preview
          </h1>
          <p className="text-sm text-muted-foreground">
            Generate the markdown for the monthly r/Wilmington post. Dry-run only —
            nothing gets published from here yet.
          </p>
        </div>
        <Button variant="outline" onClick={fetchPreviews} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
          Refresh
        </Button>
      </div>

      {/* Controls row */}
      <Card className="mb-6 dark:border-white/10">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <Calendar className="h-3 w-3" /> Month
              </label>
              <Input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="w-[180px]"
                data-testid="reddit-month"
              />
            </div>

            <label className="flex items-center gap-2 cursor-pointer pb-2">
              <input
                type="checkbox"
                checked={includeTickets}
                onChange={(e) => setIncludeTickets(e.target.checked)}
                className="rounded h-4 w-4"
                data-testid="include-tickets"
              />
              <span className="text-sm">
                Include external ticket links
                <span className="block text-xs text-muted-foreground">
                  Adds "[tickets](Ticketmaster/SeatGeek)" to ticketed events. Off by default
                  for the cleanest, least-promotional read.
                </span>
              </span>
            </label>

            {data && (
              <div className="flex items-center gap-2 ml-auto">
                <Badge variant="secondary">
                  {data.event_count} {data.event_count === 1 ? 'event' : 'events'} in {data.month_label}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Suggested post title (same across all styles) */}
      {data?.title && (
        <Card className="mb-6 dark:border-white/10">
          <CardContent className="p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Suggested post title</p>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <p className="font-medium">{data.title}</p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => copyMarkdown('title', data.title)}
              >
                <Copy className="h-3 w-3 mr-1" /> Copy
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Style tabs */}
      {loading && !data ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : data ? (
        <Tabs defaultValue="weekly" className="w-full">
          <TabsList className="grid grid-cols-3 mb-4">
            {STYLES.map((s) => (
              <TabsTrigger key={s.value} value={s.value} data-testid={`tab-${s.value}`}>
                {s.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {STYLES.map((s) => {
            const styleData = data.styles?.[s.value];
            if (!styleData) return null;
            return (
              <TabsContent key={s.value} value={s.value}>
                <Card className="dark:border-white/10">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
                      <h3 className="font-heading font-semibold">{styleData.label}</h3>
                      <Button
                        size="sm"
                        onClick={() => copyMarkdown(s.value, styleData.markdown)}
                        data-testid={`copy-${s.value}`}
                      >
                        {copiedStyle === s.value ? (
                          <><Check className="h-4 w-4 mr-1" /> Copied</>
                        ) : (
                          <><Copy className="h-4 w-4 mr-1" /> Copy markdown</>
                        )}
                      </Button>
                    </div>

                    <pre
                      className="bg-muted/50 dark:bg-muted/30 border border-border rounded-lg p-4 text-xs overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed max-h-[600px] overflow-y-auto"
                      data-testid={`markdown-${s.value}`}
                    >
                      {styleData.markdown}
                    </pre>
                  </CardContent>
                </Card>
              </TabsContent>
            );
          })}
        </Tabs>
      ) : (
        <div className="text-center py-16 text-muted-foreground">
          No data — try refresh.
        </div>
      )}

      {/* How to use this page */}
      <Card className="mt-8 bg-muted/30 dark:border-white/10">
        <CardContent className="p-4 text-sm text-muted-foreground space-y-2">
          <p className="font-medium text-foreground">How to use this page</p>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Pick a month above (defaults to next month).</li>
            <li>Switch between the three style tabs to compare formats.</li>
            <li>Click <strong>Copy markdown</strong> on the style you want to share.</li>
            <li>
              Paste into a Reddit post draft on r/Wilmington. For the community-vote
              post, paste all three into one draft (with a short intro asking which
              format people prefer).
            </li>
            <li>
              <strong>Don't publish from here.</strong> Live posting machinery isn't
              wired up yet — this is preview-only by design.
            </li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

// "YYYY-MM" for next month — matches the backend default for consistency
// (the user can override via the month picker).
function defaultMonth() {
  const now = new Date();
  // Jumping forward by 32 days then snapping to day 1 reliably crosses
  // any month boundary regardless of how many days the current month has.
  const nxt = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return `${nxt.getFullYear()}-${String(nxt.getMonth() + 1).padStart(2, '0')}`;
}
