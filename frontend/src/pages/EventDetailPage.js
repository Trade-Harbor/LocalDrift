import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';
import { Textarea } from '../components/ui/textarea';
import { toast } from 'sonner';
import { useAuth } from '../context/AuthContext';
import { useLocation as useLocationContext } from '../context/LocationContext';
import { format } from 'date-fns';
import ReportButton from '../components/ReportButton';
import {
  Calendar,
  Clock,
  MapPin,
  Users,
  Ticket,
  Star,
  Share2,
  Heart,
  MessageCircle,
  ArrowLeft,
  ExternalLink,
  Sparkles,
  Pencil
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function EventDetailPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Admin override token from URL — when present, an "Admin: force-delete"
  // button appears for any event regardless of organizer. Used for moderation
  // and for cleaning up bulk-imported events that have organizer_id="system_admin"
  // and therefore can't be deleted via the normal organizer flow.
  const adminToken = searchParams.get('admin_token') || '';
  const { user, isAuthenticated, token } = useAuth();
  const { location } = useLocationContext();
  
  const [event, setEvent] = useState(null);
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newComment, setNewComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [ticketQuantity, setTicketQuantity] = useState(1);
  const [promotionPackages, setPromotionPackages] = useState([]);
  const [promoting, setPromoting] = useState(false);

  useEffect(() => {
    fetchEvent();
    fetchComments();
  }, [eventId]);

  // Fetch promotion packages when current user is the organizer of an unpromoted event
  useEffect(() => {
    if (event && user && event.organizer_id === user.user_id && !event.is_promoted) {
      axios
        .get(`${API_URL}/api/payments/promotion-packages`)
        .then((res) => setPromotionPackages(res.data || []))
        .catch(() => setPromotionPackages([]));
    }
  }, [event, user]);

  const handlePromoteEvent = async (packageId) => {
    if (!isAuthenticated) {
      toast.error('Please login to promote this event');
      navigate('/login');
      return;
    }
    setPromoting(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/payments/checkout/promotion`,
        null,
        {
          params: { event_id: eventId, package_id: packageId },
          headers: {
            Authorization: `Bearer ${token}`,
            Origin: window.location.origin,
          },
        }
      );
      window.location.href = response.data.checkout_url;
    } catch (error) {
      console.error('Promotion error:', error);
      toast.error(error.response?.data?.detail || 'Failed to start promotion checkout');
    } finally {
      setPromoting(false);
    }
  };

  const handleAdminForceDelete = async () => {
    const title = event?.title || 'this event';
    const ok = window.confirm(
      `Force-delete "${title}"?\n\nThis bypasses the organizer check and cannot be undone. ` +
      `Comments and reports tied to this event will also be removed.`
    );
    if (!ok) return;
    try {
      const res = await axios.delete(`${API_URL}/api/admin/events/${eventId}`, {
        params: { token: adminToken },
      });
      const cascade = res.data?.cascade || {};
      const cascadeMsg = [
        cascade.comments_removed ? `${cascade.comments_removed} comments` : null,
        cascade.reports_removed ? `${cascade.reports_removed} reports` : null,
        cascade.tickets_flagged ? `${cascade.tickets_flagged} tickets flagged` : null,
      ].filter(Boolean).join(', ');
      toast.success(cascadeMsg ? `Event deleted (${cascadeMsg})` : 'Event deleted');
      navigate('/events');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Admin delete failed');
    }
  };

  const fetchEvent = async () => {
    try {
      const params = {};
      if (location) {
        params.latitude = location.latitude;
        params.longitude = location.longitude;
      }
      const response = await axios.get(`${API_URL}/api/events/${eventId}`, { params });
      setEvent(response.data);
    } catch (error) {
      console.error('Error fetching event:', error);
      toast.error('Event not found');
      navigate('/events');
    } finally {
      setLoading(false);
    }
  };

  const fetchComments = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/comments/event/${eventId}`);
      setComments(response.data);
    } catch (error) {
      console.error('Error fetching comments:', error);
    }
  };

  const handleComment = async (e) => {
    e.preventDefault();
    if (!isAuthenticated) {
      toast.error('Please login to comment');
      navigate('/login');
      return;
    }

    if (!newComment.trim()) return;

    setSubmitting(true);
    try {
      await axios.post(
        `${API_URL}/api/comments?target_type=event&target_id=${eventId}`,
        { content: newComment },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNewComment('');
      fetchComments();
      toast.success('Comment posted!');
    } catch (error) {
      toast.error('Failed to post comment');
    } finally {
      setSubmitting(false);
    }
  };

  const handlePurchaseTicket = async () => {
    // Externally-ingested events (Ticketmaster, SeatGeek) link out to the
    // original ticketing site instead of using LocalDrift's Stripe checkout —
    // we don't actually sell those tickets ourselves.
    if (event.external_url) {
      window.open(event.external_url, '_blank', 'noopener,noreferrer');
      return;
    }

    if (!isAuthenticated) {
      toast.error('Please login to purchase tickets');
      navigate('/login');
      return;
    }

    setPurchasing(true);
    try {
      const response = await axios.post(
        `${API_URL}/api/payments/checkout/ticket`,
        {
          event_id: eventId,
          quantity: ticketQuantity,
          payment_method: 'stripe'
        },
        {
          headers: {
            Authorization: `Bearer ${token}`,
            Origin: window.location.origin
          }
        }
      );

      // Redirect to Stripe checkout
      window.location.href = response.data.checkout_url;
    } catch (error) {
      console.error('Purchase error:', error);
      toast.error(error.response?.data?.detail || 'Failed to process purchase');
    } finally {
      setPurchasing(false);
    }
  };

  const handleShare = async () => {
    try {
      await navigator.share({
        title: event.title,
        text: event.description,
        url: window.location.href
      });
    } catch {
      // Fallback to copy link
      navigator.clipboard.writeText(window.location.href);
      toast.success('Link copied to clipboard!');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-4 py-8 max-w-6xl">
          <div className="animate-pulse space-y-6">
            <div className="h-96 bg-muted rounded-2xl" />
            <div className="h-8 bg-muted rounded w-3/4" />
            <div className="h-4 bg-muted rounded w-1/2" />
          </div>
        </div>
      </div>
    );
  }

  if (!event) return null;

  const startDate = new Date(event.start_date);
  const endDate = event.end_date ? new Date(event.end_date) : null;
  const ticketsRemaining = event.total_tickets ? event.total_tickets - event.tickets_sold : null;
  const hasDiscount = event.discount_percentage > 0;
  const finalPrice = event.discounted_price || event.ticket_price;

  return (
    <div className="min-h-screen bg-background" data-testid="event-detail-page">
      {/* Hero Image */}
      <div className="relative h-[400px] md:h-[500px] overflow-hidden">
        <img
          src={event.image_url || 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200'}
          alt={event.title}
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/50 to-transparent" />
        
        {/* Back Button */}
        <Button
          variant="ghost"
          size="icon"
          className="absolute top-4 left-4 bg-white/20 backdrop-blur-sm hover:bg-white/30 rounded-full"
          onClick={() => navigate(-1)}
          data-testid="back-btn"
        >
          <ArrowLeft className="h-5 w-5 text-white" />
        </Button>

        {/* Actions */}
        <div className="absolute top-4 right-4 flex gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="bg-white/20 backdrop-blur-sm hover:bg-white/30 rounded-full"
            onClick={handleShare}
            data-testid="share-btn"
          >
            <Share2 className="h-5 w-5 text-white" />
          </Button>
        </div>

        {/* Badges */}
        <div className="absolute bottom-6 left-6 flex flex-wrap gap-2">
          {event.is_promoted && (
            <Badge className="bg-gradient-to-r from-indigo-500 to-pink-500 text-white">
              <Star className="h-3 w-3 mr-1" /> Featured
            </Badge>
          )}
          {!event.is_paid && (
            <Badge className="bg-accent text-white">Free Event</Badge>
          )}
          <Badge variant="secondary" className="backdrop-blur-sm">
            {event.category.replace('_', ' ')}
          </Badge>
        </div>
      </div>

      <div className="container mx-auto px-4 md:px-6 lg:px-8 max-w-6xl -mt-20 relative z-10 pb-12">
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-2 space-y-8">
            {/* Title & Description */}
            <div className="bg-card rounded-2xl p-6 md:p-8 shadow-lg dark:border dark:border-white/10">
              <h1 className="font-heading text-3xl md:text-4xl font-bold mb-4">
                {event.title}
              </h1>

              <div className="flex items-center gap-4 mb-6">
                <Avatar className="h-10 w-10">
                  <AvatarFallback className="bg-primary text-primary-foreground">
                    {event.organizer_name?.charAt(0)}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p className="font-medium">{event.organizer_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {event.organizer_type === 'business' ? 'Business' : 'Community Organizer'}
                  </p>
                </div>
              </div>

              <p className="text-muted-foreground leading-relaxed whitespace-pre-wrap">
                {event.description}
              </p>

              {/* Tags */}
              {event.tags?.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-6">
                  {event.tags.map((tag, idx) => (
                    <Badge key={idx} variant="outline">
                      #{tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {/* Event Details */}
            <div className="bg-card rounded-2xl p-6 md:p-8 shadow-lg dark:border dark:border-white/10">
              <h2 className="font-heading text-xl font-semibold mb-6">Event Details</h2>

              <div className="space-y-4">
                <div className="flex items-start gap-4">
                  <div className="p-3 bg-primary/10 rounded-xl">
                    <Calendar className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <p className="font-medium">{format(startDate, 'EEEE, MMMM d, yyyy')}</p>
                    <p className="text-sm text-muted-foreground">
                      {format(startDate, 'h:mm a')}
                      {endDate && ` - ${format(endDate, 'h:mm a')}`}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="p-3 bg-secondary/10 rounded-xl">
                    <MapPin className="h-5 w-5 text-secondary" />
                  </div>
                  <div>
                    <p className="font-medium">{event.location_name}</p>
                    <p className="text-sm text-muted-foreground">
                      {event.address}, {event.city}, {event.state} {event.zip_code}
                    </p>
                    {event.distance !== undefined && (
                      <p className="text-sm text-muted-foreground mt-1">
                        {event.distance} miles away
                      </p>
                    )}
                    <Button
                      variant="link"
                      className="p-0 h-auto text-sm"
                      onClick={() => window.open(
                        `https://www.google.com/maps/search/?api=1&query=${event.latitude},${event.longitude}`,
                        '_blank'
                      )}
                    >
                      Get Directions <ExternalLink className="h-3 w-3 ml-1" />
                    </Button>
                  </div>
                </div>

                {ticketsRemaining !== null && (
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-accent/10 rounded-xl">
                      <Users className="h-5 w-5 text-accent" />
                    </div>
                    <div>
                      <p className="font-medium">{ticketsRemaining} tickets remaining</p>
                      <p className="text-sm text-muted-foreground">
                        {event.tickets_sold} tickets sold
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Comments Section */}
            <div className="bg-card rounded-2xl p-6 md:p-8 shadow-lg dark:border dark:border-white/10">
              <h2 className="font-heading text-xl font-semibold mb-6 flex items-center gap-2">
                <MessageCircle className="h-5 w-5" />
                Comments ({comments.length})
              </h2>

              {/* Comment Form */}
              <form onSubmit={handleComment} className="mb-6">
                <Textarea
                  placeholder={isAuthenticated ? "Share your thoughts..." : "Login to comment"}
                  value={newComment}
                  onChange={(e) => setNewComment(e.target.value)}
                  disabled={!isAuthenticated || submitting}
                  className="mb-3"
                  data-testid="comment-input"
                />
                <Button
                  type="submit"
                  disabled={!isAuthenticated || !newComment.trim() || submitting}
                  className="rounded-full"
                  data-testid="submit-comment-btn"
                >
                  {submitting ? 'Posting...' : 'Post Comment'}
                </Button>
              </form>

              {/* Comments List */}
              <div className="space-y-4">
                {comments.length === 0 ? (
                  <p className="text-center text-muted-foreground py-8">
                    No comments yet. Be the first to share your thoughts!
                  </p>
                ) : (
                  comments.map((comment) => (
                    <div key={comment.comment_id} className="flex gap-3 p-4 bg-muted/50 rounded-xl">
                      <Avatar className="h-10 w-10">
                        <AvatarImage src={comment.user_picture} />
                        <AvatarFallback className="bg-primary text-primary-foreground text-sm">
                          {comment.user_name?.charAt(0)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-medium text-sm">{comment.user_name}</span>
                          <span className="text-xs text-muted-foreground">
                            {format(new Date(comment.created_at), 'MMM d, yyyy')}
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground">{comment.content}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Sidebar - Ticket Purchase */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 bg-card rounded-2xl p-6 shadow-lg dark:border dark:border-white/10">
              {event.external_url ? (
                // External event (Ticketmaster / SeatGeek) — link out for tickets.
                // We don't sell these directly, so skip the qty selector + subtotal.
                <>
                  <div className="text-center mb-6">
                    {event.ticket_price && (
                      <>
                        <span className="text-sm text-muted-foreground">From</span>
                        <div className="flex items-center justify-center gap-2">
                          <span className="text-3xl font-bold">${event.ticket_price}</span>
                        </div>
                      </>
                    )}
                    {!event.ticket_price && (
                      <p className="text-lg font-semibold">Tickets available</p>
                    )}
                    <Badge variant="secondary" className="mt-2">
                      via {event.source ? event.source.charAt(0).toUpperCase() + event.source.slice(1) : 'partner site'}
                    </Badge>
                  </div>
                  <Button
                    className="w-full rounded-full bg-gradient-to-r from-indigo-500 to-pink-500 hover:opacity-90"
                    size="lg"
                    onClick={handlePurchaseTicket}
                    data-testid="buy-tickets-btn"
                  >
                    <Ticket className="h-4 w-4 mr-2" />
                    Get Tickets
                    <ExternalLink className="h-3 w-3 ml-2" />
                  </Button>
                  <p className="text-xs text-center text-muted-foreground mt-3">
                    You'll be redirected to complete your purchase.
                  </p>
                </>
              ) : event.is_paid ? (
                // User-submitted paid event during beta — internal Stripe checkout
                // is disabled. Show price info + "tickets coming soon" rather than
                // attempting a checkout that the backend would reject anyway.
                <>
                  <div className="text-center mb-6">
                    <span className="text-sm text-muted-foreground">From</span>
                    <div className="flex items-center justify-center gap-2">
                      <span className="text-3xl font-bold">${finalPrice ?? event.ticket_price ?? '—'}</span>
                      <span className="text-muted-foreground">/ ticket</span>
                    </div>
                    <Badge variant="secondary" className="mt-2">Beta — ticketing coming soon</Badge>
                  </div>
                  <div className="bg-muted/50 rounded-xl p-4 mb-4 text-sm text-center text-muted-foreground">
                    Ticket purchases are disabled during the LocalDrift beta. Contact the
                    event organizer directly, or reach out to{' '}
                    <a href="mailto:hello@localdrift.app" className="underline text-primary">us</a>
                    {' '}if you'd like an early-access slot for selling tickets through LocalDrift.
                  </div>
                </>
              ) : (
                <div className="text-center">
                  <Badge className="bg-accent text-white text-lg px-4 py-1 mb-4">
                    Free Event
                  </Badge>
                  <p className="text-muted-foreground mb-4">
                    No tickets required. Just show up and enjoy!
                  </p>
                  <Button
                    variant="outline"
                    className="w-full rounded-full"
                    onClick={() => window.open(
                      `https://www.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(event.title)}&dates=${format(startDate, "yyyyMMdd'T'HHmmss")}/${endDate ? format(endDate, "yyyyMMdd'T'HHmmss") : format(startDate, "yyyyMMdd'T'HHmmss")}&location=${encodeURIComponent(event.address)}`,
                      '_blank'
                    )}
                    data-testid="add-to-calendar-btn"
                  >
                    <Calendar className="h-4 w-4 mr-2" />
                    Add to Calendar
                  </Button>
                </div>
              )}
            </div>

            {/* Promote This Event — beta-mode soft message for organizers */}
            {user && event.organizer_id === user.user_id && !event.is_promoted && (
              <div className="mt-4 bg-card rounded-2xl p-6 shadow-lg dark:border dark:border-white/10" data-testid="promote-event-card">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="h-5 w-5 text-amber-500" />
                  <h3 className="font-heading text-lg font-semibold">Promote This Event</h3>
                </div>
                <p className="text-sm text-muted-foreground mb-3">
                  Featured placement is launching after the LocalDrift beta. Want early access?
                </p>
                <Button variant="outline" className="w-full rounded-full" asChild>
                  <a href="mailto:hello@localdrift.app?subject=LocalDrift%20Promotion%20Early%20Access">
                    Email us about early access
                  </a>
                </Button>
              </div>
            )}

            {/* Already promoted indicator */}
            {user && event.organizer_id === user.user_id && event.is_promoted && (
              <div className="mt-4 bg-card rounded-2xl p-4 shadow-lg dark:border dark:border-white/10 flex items-center gap-2" data-testid="event-promoted-badge">
                <Sparkles className="h-4 w-4 text-amber-500" />
                <span className="text-sm">This event is currently promoted.</span>
              </div>
            )}

            {/* Non-organizer report button. Hidden for the organizer (they
                wouldn't report their own event) and unauthenticated users
                see a "sign in" toast on click. */}
            {(!user || event.organizer_id !== user.user_id) && (
              <div className="mt-4 flex justify-end">
                <ReportButton targetType="event" targetId={event.event_id} variant="text" />
              </div>
            )}

            {/* Organizer-only edit control. Edit page hosts the Delete
                button in its danger zone, so this is one CTA instead of
                two. Backend separately enforces ownership on PUT/DELETE. */}
            {user && event.organizer_id === user.user_id && (
              <div className="mt-4 bg-card rounded-2xl p-4 shadow-lg dark:border dark:border-white/10" data-testid="organizer-controls">
                <p className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
                  Organizer controls
                </p>
                <Button
                  variant="outline"
                  className="w-full rounded-full"
                  onClick={() => navigate(`/events/${event.event_id}/edit`)}
                  data-testid="edit-event-btn"
                >
                  <Pencil className="h-4 w-4 mr-2" />
                  Edit event
                </Button>
              </div>
            )}

            {/* Admin force-delete block. Only renders when ?admin_token=
                is in the URL — the token is validated server-side on
                submit; if it's wrong the API call 401s and nothing
                happens. Visually distinct from the organizer Edit/Delete
                so it's clear this is a moderation action, not a self-
                service one. */}
            {adminToken && (
              <div className="mt-4 bg-card rounded-2xl p-4 shadow-lg dark:border dark:border-red-500/30 border-red-200/50" data-testid="admin-controls">
                <p className="text-xs uppercase tracking-wide text-red-600 dark:text-red-400 mb-2">
                  Admin override
                </p>
                <p className="text-xs text-muted-foreground mb-3">
                  Force-deletes this event regardless of organizer. Used for moderation
                  and to clean up bulk-imported events. Comments + reports also removed;
                  tickets flagged.
                </p>
                <Button
                  variant="outline"
                  className="w-full rounded-full border-red-300 text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950/30"
                  onClick={handleAdminForceDelete}
                  data-testid="admin-force-delete-btn"
                >
                  Force-delete event
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
