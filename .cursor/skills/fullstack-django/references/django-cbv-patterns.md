# Django CBV Patterns

Use this reference only when the task is specifically about class-based views.

## Choose CBV vs FBV

Prefer CBVs when:

- the flow matches CRUD or generic view patterns
- queryset shaping and permissions are reusable
- multiple similar views share mixins or behavior

Prefer FBVs when:

- the logic is a small one-off endpoint
- the flow is highly custom or multi-branch
- the view coordinates several unrelated models in a bespoke way

## Canonical CBV Structure

```python
class ExampleUpdateView(LoginRequiredMixin, UpdateView):
    model = Example
    form_class = ExampleForm

    def get_queryset(self):
        return super().get_queryset().select_related("owner")

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("example-detail", kwargs={"pk": self.object.pk})
```

## Mixins And Ordering

- order permission/auth mixins first
- put reusable behavior mixins next
- keep the Django generic base view last
- call `super()` consistently in overridden methods

## Methods To Reach For First

- `get_queryset()` for filtering and query optimization
- `get_context_data()` for extra template context
- `get_form_kwargs()` for injecting request-dependent form data
- `form_valid()` and `form_invalid()` for write-time behavior
- `get_success_url()` for dynamic redirects

## Common Pitfalls

- wrong MRO because the base view is placed before mixins
- authorization logic buried in templates only
- heavy business logic in `dispatch()` or `get()`
- queryset defined once as a class attribute when it really depends on the request
- stale AJAX patterns such as `request.is_ajax()`

## Testing Focus

- test permission boundaries
- test queryset filtering and query count on hot paths
- test valid and invalid form submissions
- use `RequestFactory` for narrow unit tests and the Django test client for integration flows
