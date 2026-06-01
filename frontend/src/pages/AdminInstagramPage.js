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

  const [weekStart, setWeekStart] = useState(defaultMonday());
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [data, setData] = useState(null);

  const fetchPreview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/instagram/preview`, {
        params: { token, week_start: weekStart },
      });
      setData(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not load preview');
    } finally {
      setLoading(false);
    }
  }, [token, weekStart]);

  useEffect(() => { fetchPreview(); }, [fetchPreview]);

  const downloadZip = async () => {
    if (!token) return;
    setDownloading(true);
    try {
      const res = await axios.get(`${API_URL}/api/admin/instagram/download`, {
        params: { token, week_start: weekStart },
        responseType: 'blob',
      });
      // Trigger a browser download
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      // Server sent a Content-Disposition header — extract filename if present
      const cd = res.headers['content-disposition'] || '';
      const match = /filename="?([^";]+)"?/.exec(cd);
      a.download = match ? match[1] : `localdrift_carousel_${weekStart}.zip`;
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

      {/* Week picker + metadata */}
      <Card className="mb-6 dark:border-white/10">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                <Calendar className="h-3 w-3" /> Week starting (Monday)
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
                <Badge className="bg-primary/80">{data.week_label}</Badge>
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
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`;
}
