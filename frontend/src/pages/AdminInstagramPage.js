import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import {
  Instagram, Loader2, RefreshCw, Calendar, Download,
} from 'lucide-react';
import { toast } from 'sonner';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Admin: Instagram carousel generator.
 *
 * Pick a week (defaults to next Monday in ET), preview the 1080x1080
 * slides as thumbnails, download the full-resolution PNGs as a ZIP
 * ready for IG upload.
 *
 * Auth: ?token=ADMIN_TOKEN in URL. Same pattern as the other admin pages.
 */

export default function AdminInstagramPage() {
  usePageTitle('Admin · Instagram');
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  // Mode controls the date window:
  //   "week"    — Mon-Sun (7 days, the full week)
  //   "weekday" — Mon-Fri (5 days, no weekend)
  //   "weekend" — Fri-Sun (3 days, weekend only)
  // Date picker anchor changes meaning per mode (Monday for week/weekday,
  // Friday for weekend).
  const [mode, setMode] = useState('week');
  const [weekStart, setWeekStart] = useState(defaultMonday());
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [data, setData] = useState(null);

  // When the mode flips, swap the anchor date so the picker is showing
  // the right kind of day-of-week. Avoids the situation where user
  // switches to weekend mode but the picker still has a Monday in it,
  // confusing the resulting window.
  const handleModeChange = (newMode) => {
    setMode(newMode);
    // Weekend mode anchors on a Friday; week + weekday both anchor on a Monday.
    setWeekStart(newMode === 'weekend' ? defaultFriday() : defaultMonday());
  };

  const fetchPreview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/instagram/preview`, {
        params: { token, week_start: weekStart, mode },
      });
      setData(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load preview');
    } finally {
      setLoading(false);
    }
  }, [token, weekStart, mode]);

  useEffect(() => { fetchPreview(); }, [fetchPreview]);

  const downloadZip = async () => {
    if (!token) return;
    setDownloading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/instagram/download`, {
        params: { token, week_start: weekStart, mode },
        responseType: 'blob',
      });
      // Trigger a browser download
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      // Server sent a Content-Disposition header — extract filename if present
      const cd = res.headers['content-disposition'] || '';
      const match = /filename="?([^";]+)"?/.exec(cd);
      a.download = match ? match[1] : `localdrift_carousel_${mode}_${weekStart}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success('ZIP downloaded — unzip and upload to Instagram in order');
    } catch (err) {
      toast.error('Download failed');
    } finally {
      setDownloading(false);
    }
  };

  if (!token) {
    return (
      <div className="container mx-auto max-w-xl py-16 px-4">
        <h1 className="font-heading text-2xl font-bold mb-2">Admin · Instagram</h1>
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
            <Instagram className="h-6 w-6 text-primary" />
            Instagram carousel
          </h1>
          <p className="text-sm text-muted-foreground">
            Generates a weekly events carousel (1080x1080 PNGs) for upload to @localdrift.app.
          </p>
        </div>
        <Button variant="outline" onClick={fetchPreview} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-1" />}
          Refresh
        </Button>
      </div>

      {/* Mode + date picker + metadata */}
      <Card className="mb-6 dark:border-white/10">
        <CardContent className="p-4">
          {/* Mode toggle row */}
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            <span className="text-xs font-medium text-muted-foreground mr-1">Format:</span>
            <Button
              variant={mode === 'week' ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleModeChange('week')}
              className="rounded-full"
              data-testid="ig-mode-week"
            >
              Full week (Mon–Sun)
            </Button>
            <Button
              variant={mode === 'weekday' ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleModeChange('weekday')}
              className="rounded-full"
              data-testid="ig-mode-weekday"
            >
              Weekdays (Mon–Fri)
            </Button>
            <Button
              variant={mode === 'weekend' ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleModeChange('weekend')}
              className="rounded-full"
              data-testid="ig-mode-weekend"
            >
              Weekend (Fri–Sun)
            </Button>
          </div>

          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {mode === 'weekend' ? 'Weekend starting (Friday)' : 'Week starting (Monday)'}
              </label>
              <Input
                type="date"
                value={weekStart}
                onChange={(e) => setWeekStart(e.target.value)}
                className="w-[180px]"
                data-testid="ig-week-start"
              />
            </div>

            {data && (
              <div className="flex items-center gap-2 ml-auto flex-wrap">
                <Badge variant="secondary">{data.event_count} events</Badge>
                <Badge variant="outline">{data.slide_count} slides</Badge>
                <Badge className="bg-primary/80">
                  {data.period_label || 'this week'} · {data.week_label}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Slide grid */}
      {loading && !data ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : data?.slides?.length ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 mb-6">
            {data.slides.map((s) => (
              <div
                key={s.index}
                className="aspect-square overflow-hidden rounded-xl border border-border bg-muted/30 relative"
                data-testid={`ig-slide-${s.index}`}
              >
                <img
                  src={s.preview}
                  alt={`Slide ${s.index + 1}`}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
                <div className="absolute top-1 left-1 bg-black/60 text-white text-[10px] font-mono px-1.5 py-0.5 rounded">
                  {s.index + 1}
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {data.slide_count} slides at 1080×1080. Upload in carousel order
              (slide_00 first, then slide_01, etc.).
            </p>
            <Button onClick={downloadZip} disabled={downloading} className="rounded-full">
              {downloading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Download className="h-4 w-4 mr-1" />}
              Download ZIP
            </Button>
          </div>
        </>
      ) : (
        <div className="text-center py-16 text-muted-foreground">
          No slides — try refreshing.
        </div>
      )}

      {/* How to use */}
      <Card className="mt-8 bg-muted/30 dark:border-white/10">
        <CardContent className="p-4 text-sm text-muted-foreground space-y-2">
          <p className="font-medium text-foreground">How to use this page</p>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Pick the Monday of the target week. Defaults to next Monday.</li>
            <li>Review the slide thumbnails. If you don't like the events selected, hand-import / update events for that week first, then refresh here.</li>
            <li>Click <strong>Download ZIP</strong> — unzips into <code>slide_00.png</code> through <code>slide_NN.png</code>.</li>
            <li>Open Instagram on your phone, create a new post, select multiple, pick the slides in order (00 first).</li>
            <li>Caption + hashtags are not generated — write those manually for now (each week is different).</li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

// Default to next Monday in user's local timezone. Close enough to ET
// for most weeks since the backend resolves the exact Mon-Sun window in ET.
function defaultMonday() {
  const now = new Date();
  const daysUntilMonday = (8 - now.getDay()) % 7 || 7;
  const next = new Date(now);
  next.setDate(now.getDate() + daysUntilMonday);
  return formatDate(next);
}

// Default to the next upcoming Friday. If today IS Friday, use today
// (a Friday-morning post for "this weekend" still wants today's window).
function defaultFriday() {
  const now = new Date();
  // JS getDay(): Sun=0, Mon=1, ..., Fri=5, Sat=6
  const daysUntilFriday = (5 - now.getDay() + 7) % 7;
  const next = new Date(now);
  next.setDate(now.getDate() + daysUntilFriday);
  return formatDate(next);
}

function formatDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
