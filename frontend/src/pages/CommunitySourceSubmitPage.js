import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Label } from '../components/ui/label';
import { Card, CardContent } from '../components/ui/card';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import {
  ArrowLeft, Megaphone, Plus, Trash2, CheckCircle2, Loader2, AlertCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import usePageTitle from '../hooks/usePageTitle';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Keep in sync with the backend's COMMUNITY_SOURCE_CATEGORIES set and
// CommunitySourcesPage's CATEGORIES list.
const CATEGORIES = [
  { value: 'subreddit',      label: 'Subreddit' },
  { value: 'facebook_group', label: 'Facebook group' },
  { value: 'facebook_page',  label: 'Facebook page' },
  { value: 'instagram',      label: 'Instagram' },
  { value: 'tiktok',         label: 'TikTok' },
  { value: 'youtube',        label: 'YouTube' },
  { value: 'blog',           label: 'Blog' },
  { value: 'newsletter',     label: 'Newsletter' },
  { value: 'podcast',        label: 'Podcast' },
  { value: 'other',          label: 'Other' },
];

/**
 * Public submission form for the community sources directory.
 * No auth required; if the visitor is signed in we attach their user_id
 * server-side so we can DM them about their submission. Otherwise they
 * provide an email.
 *
 * Flow:
 *   1. Fill form (name, description, category, tags, at least one link)
 *   2. Submit → backend stores status=pending
 *   3. Show success card with a "back to directory" CTA
 *
 * Special case: 409 means slug collision — surface the existing record's
 * status so the user knows "you're already in the queue" rather than a
 * generic "submission failed" error.
 */
export default function CommunitySourceSubmitPage() {
  usePageTitle('Submit a community source');
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [coverageTagsInput, setCoverageTagsInput] = useState('');
  const [links, setLinks] = useState([{ platform: '', url: '', handle: '' }]);
  const [submitterEmail, setSubmitterEmail] = useState(user?.email || '');
  const [submitterName, setSubmitterName] = useState(user?.name || '');

  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(null); // { sourceId } when done
  const [duplicate, setDuplicate] = useState(null); // existing record from 409

  const updateLink = (idx, field, value) => {
    setLinks((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  };
  const addLink = () => setLinks((prev) => [...prev, { platform: '', url: '', handle: '' }]);
  const removeLink = (idx) => setLinks((prev) => prev.filter((_, i) => i !== idx));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setDuplicate(null);

    // Client-side validation (server re-validates, but fail fast).
    if (name.trim().length < 3 || name.trim().length > 80) {
      toast.error('Name must be 3-80 characters');
      return;
    }
    if (!category) {
      toast.error('Pick a category');
      return;
    }
    const cleanLinks = links
      .map((l) => ({
        platform: (l.platform || '').trim(),
        url: (l.url || '').trim(),
        handle: (l.handle || '').trim() || null,
      }))
      .filter((l) => l.url);
    if (cleanLinks.length === 0) {
      toast.error('Add at least one link');
      return;
    }
    if (!submitterEmail.trim()) {
      toast.error('Email is required so we can follow up');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        category,
        coverage_tags: coverageTagsInput
          .split(',')
          .map((t) => t.trim().toLowerCase())
          .filter(Boolean)
          .slice(0, 10),
        links: cleanLinks,
        submitter_email: submitterEmail.trim(),
        submitter_name: submitterName.trim() || null,
      };
      const res = await axios.post(`${API_URL}/api/community-sources`, payload);
      setSuccess({ sourceId: res.data.source_id });
    } catch (err) {
      if (err.response?.status === 409) {
        // Backend returned the existing record — show it to the user.
        const detail = err.response.data?.detail || {};
        setDuplicate({
          existing: detail.existing,
          existingStatus: detail.existing_status,
        });
      } else {
        const msg = err.response?.data?.detail || 'Could not submit. Try again?';
        toast.error(typeof msg === 'string' ? msg : 'Submission failed');
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <Card className="w-full max-w-md dark:border-white/10">
          <CardContent className="p-8 text-center">
            <CheckCircle2 className="h-12 w-12 text-emerald-500 mx-auto mb-4" />
            <h1 className="font-heading text-2xl font-bold mb-2">Submitted</h1>
            <p className="text-muted-foreground mb-6">
              Thanks! An admin will review your submission within a few days. You'll see
              your listing appear in the directory once approved.
            </p>
            <div className="flex flex-col sm:flex-row gap-2 justify-center">
              <Button asChild variant="outline" className="rounded-full">
                <Link to="/community-sources">Back to directory</Link>
              </Button>
              <Button onClick={() => { setSuccess(null); }} className="rounded-full">
                Submit another
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background" data-testid="community-source-submit-page">
      <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-2xl py-8">
        <Button variant="ghost" size="sm" className="mb-6" asChild>
          <Link to="/community-sources">
            <ArrowLeft className="h-4 w-4 mr-1" /> Back to directory
          </Link>
        </Button>

        <div className="mb-8">
          <div className="inline-flex items-center justify-center h-12 w-12 rounded-2xl bg-primary/10 text-primary mb-4">
            <Megaphone className="h-6 w-6" />
          </div>
          <h1 className="font-heading text-3xl font-bold mb-2">Submit a local voice</h1>
          <p className="text-muted-foreground">
            Run a Wilmington subreddit, FB page, blog, podcast, or anything else local?
            Submit it here. We'll review and add it within a few days.
          </p>
        </div>

        {/* Duplicate hit */}
        {duplicate && duplicate.existing && (
          <Card className="mb-6 border-amber-300 bg-amber-50/50 dark:border-amber-700 dark:bg-amber-950/20">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-sm">
                    "{duplicate.existing.name}" is already in our queue
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Status: <span className="capitalize">{duplicate.existingStatus}</span>.
                    {duplicate.existingStatus === 'pending'
                      ? ' We\'re reviewing it.'
                      : ' Check the directory.'}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basics */}
          <Card className="dark:border-white/10">
            <CardContent className="p-6 space-y-4">
              <h2 className="font-heading text-lg font-semibold">Basics</h2>

              <div className="space-y-2">
                <Label htmlFor="source-name">Name *</Label>
                <Input
                  id="source-name"
                  placeholder="e.g. r/Wilmington, Wilmington Foodies, Carolina Coast Podcast"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={80}
                  required
                  data-testid="submit-name"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="source-category">Category *</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger id="source-category" data-testid="submit-category">
                    <SelectValue placeholder="What kind of source is this?" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="source-description">
                  Description <span className="text-muted-foreground">(up to 500 chars)</span>
                </Label>
                <Textarea
                  id="source-description"
                  placeholder="What does this source cover? Who would benefit from following it?"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  rows={4}
                  data-testid="submit-description"
                />
                <p className="text-xs text-muted-foreground text-right">
                  {description.length} / 500
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="source-tags">
                  Coverage tags <span className="text-muted-foreground">(comma-separated, optional)</span>
                </Label>
                <Input
                  id="source-tags"
                  placeholder="food, music, family, news, outdoors"
                  value={coverageTagsInput}
                  onChange={(e) => setCoverageTagsInput(e.target.value)}
                  data-testid="submit-tags"
                />
              </div>
            </CardContent>
          </Card>

          {/* Links */}
          <Card className="dark:border-white/10">
            <CardContent className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="font-heading text-lg font-semibold">Links *</h2>
                <Button type="button" variant="outline" size="sm" onClick={addLink} className="rounded-full">
                  <Plus className="h-3 w-3 mr-1" /> Add another
                </Button>
              </div>
              <p className="text-xs text-muted-foreground -mt-2">
                Add at least one. The primary link comes first.
              </p>

              {links.map((lnk, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-end">
                  <div className="col-span-3">
                    <Label htmlFor={`link-platform-${idx}`} className="text-xs">Platform</Label>
                    <Input
                      id={`link-platform-${idx}`}
                      placeholder="reddit"
                      value={lnk.platform}
                      onChange={(e) => updateLink(idx, 'platform', e.target.value)}
                    />
                  </div>
                  <div className="col-span-6">
                    <Label htmlFor={`link-url-${idx}`} className="text-xs">URL</Label>
                    <Input
                      id={`link-url-${idx}`}
                      placeholder="reddit.com/r/Wilmington"
                      value={lnk.url}
                      onChange={(e) => updateLink(idx, 'url', e.target.value)}
                      data-testid={`submit-link-url-${idx}`}
                    />
                  </div>
                  <div className="col-span-2">
                    <Label htmlFor={`link-handle-${idx}`} className="text-xs">Handle</Label>
                    <Input
                      id={`link-handle-${idx}`}
                      placeholder="@x"
                      value={lnk.handle}
                      onChange={(e) => updateLink(idx, 'handle', e.target.value)}
                    />
                  </div>
                  <div className="col-span-1">
                    {links.length > 1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeLink(idx)}
                        className="text-red-500 hover:text-red-600"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Submitter */}
          <Card className="dark:border-white/10">
            <CardContent className="p-6 space-y-4">
              <h2 className="font-heading text-lg font-semibold">Your contact info</h2>
              <p className="text-xs text-muted-foreground -mt-2">
                Only used if we need to follow up about your submission. Not displayed publicly.
              </p>

              <div className="space-y-2">
                <Label htmlFor="submitter-email">Email *</Label>
                <Input
                  id="submitter-email"
                  type="email"
                  placeholder="you@example.com"
                  value={submitterEmail}
                  onChange={(e) => setSubmitterEmail(e.target.value)}
                  required
                  data-testid="submit-email"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="submitter-name">Name (optional)</Label>
                <Input
                  id="submitter-name"
                  placeholder="What should we call you?"
                  value={submitterName}
                  onChange={(e) => setSubmitterName(e.target.value)}
                />
              </div>

              {!isAuthenticated && (
                <p className="text-xs text-muted-foreground">
                  Tip: <Link to="/login" className="text-primary hover:underline">sign in first</Link>
                  {' '}so we can DM you about your submission instead of just emailing.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Submit */}
          <div className="flex gap-3 justify-end">
            <Button type="button" variant="outline" onClick={() => navigate('/community-sources')} className="rounded-full">
              Cancel
            </Button>
            <Button type="submit" disabled={submitting} className="rounded-full" data-testid="submit-btn">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Submit for review
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
