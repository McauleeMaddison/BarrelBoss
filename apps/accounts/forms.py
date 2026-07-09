import secrets
from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.text import slugify

from apps.checklists.models import Checklist, ChecklistTemplate

from .models import Organisation, StaffProfile, Venue, VenueInvite, VenueMembership


User = get_user_model()


class StaffCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput,
    )
    role = forms.ChoiceField(choices=StaffProfile.Role.choices, initial=StaffProfile.Role.STAFF)
    job_title = forms.CharField(max_length=120, required=False)
    phone = forms.CharField(max_length=40, required=False)
    is_active = forms.BooleanField(initial=True, required=False)
    notify_on_shift_assignment = forms.BooleanField(initial=True, required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args, allowed_role_values=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_role_values = set(allowed_role_values or [])
        if self.allowed_role_values:
            allowed_choices = [
                choice for choice in StaffProfile.Role.choices if choice[0] in self.allowed_role_values
            ]
            self.fields["role"].choices = allowed_choices
            if self.initial.get("role") not in self.allowed_role_values:
                self.initial["role"] = allowed_choices[0][0]

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.allowed_role_values and role not in self.allowed_role_values:
            raise forms.ValidationError("You do not have permission to assign that role.")
        return role

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
            return cleaned_data

        if password1:
            try:
                validate_password(password1)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data

    def save(self, *, venue=None, invited_by=None):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data.get("first_name", "").strip(),
            last_name=self.cleaned_data.get("last_name", "").strip(),
            email=self.cleaned_data.get("email", "").strip(),
            password=self.cleaned_data["password1"],
        )

        profile = user.staff_profile
        profile.role = self.cleaned_data["role"]
        profile.job_title = self.cleaned_data.get("job_title", "").strip()
        profile.phone = self.cleaned_data.get("phone", "").strip()
        profile.is_active = self.cleaned_data.get("is_active", False)
        profile.notify_on_shift_assignment = self.cleaned_data.get(
            "notify_on_shift_assignment",
            False,
        )
        profile.notes = self.cleaned_data.get("notes", "").strip()
        profile.save()
        if venue is not None:
            VenueMembership.objects.update_or_create(
                venue=venue,
                user=user,
                defaults={
                    "role": self.cleaned_data["role"],
                    "job_title": self.cleaned_data.get("job_title", "").strip(),
                    "notify_on_shift_assignment": self.cleaned_data.get(
                        "notify_on_shift_assignment",
                        False,
                    ),
                    "is_active": self.cleaned_data.get("is_active", False),
                    "is_default": True,
                    "invited_by": invited_by,
                },
            )
        return user


class StaffUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)

    class Meta:
        model = StaffProfile
        fields = [
            "role",
            "job_title",
            "phone",
            "is_active",
            "notify_on_shift_assignment",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(
        self,
        *args,
        user_instance,
        membership_instance=None,
        allowed_role_values=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.user_instance = user_instance
        self.membership_instance = membership_instance
        self.allowed_role_values = set(allowed_role_values or [])
        if self.allowed_role_values:
            self.fields["role"].choices = [
                choice for choice in StaffProfile.Role.choices if choice[0] in self.allowed_role_values
            ]
        self.fields["first_name"].initial = user_instance.first_name
        self.fields["last_name"].initial = user_instance.last_name
        self.fields["email"].initial = user_instance.email
        if membership_instance is not None:
            self.fields["role"].initial = membership_instance.role
            self.fields["job_title"].initial = membership_instance.job_title
            self.fields["is_active"].initial = membership_instance.is_active
            self.fields["notify_on_shift_assignment"].initial = (
                membership_instance.notify_on_shift_assignment
            )

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.allowed_role_values and role not in self.allowed_role_values:
            raise forms.ValidationError("You do not have permission to assign that role.")
        return role

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user_instance.first_name = self.cleaned_data.get("first_name", "").strip()
        self.user_instance.last_name = self.cleaned_data.get("last_name", "").strip()
        self.user_instance.email = self.cleaned_data.get("email", "").strip()

        if commit:
            self.user_instance.save(update_fields=["first_name", "last_name", "email"])
            profile.save()
            if self.membership_instance is not None:
                self.membership_instance.role = self.cleaned_data["role"]
                self.membership_instance.job_title = self.cleaned_data.get("job_title", "").strip()
                self.membership_instance.is_active = self.cleaned_data.get("is_active", False)
                self.membership_instance.notify_on_shift_assignment = self.cleaned_data.get(
                    "notify_on_shift_assignment",
                    False,
                )
                self.membership_instance.save(
                    update_fields=[
                        "role",
                        "job_title",
                        "is_active",
                        "notify_on_shift_assignment",
                        "updated_at",
                    ]
                )

        return profile


class VenueSetupForm(forms.Form):
    organisation_name = forms.CharField(max_length=180)
    venue_name = forms.CharField(max_length=180)
    venue_slug = forms.SlugField(max_length=180, required=False)
    default_shift_start_time = forms.TimeField(required=False)
    default_shift_end_time = forms.TimeField(required=False)
    low_stock_buffer_percent = forms.IntegerField(min_value=0, max_value=300, initial=50)
    supplier_names = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One supplier name per line.",
    )
    opening_checklist_items = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One opening task per line.",
    )
    closing_checklist_items = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One closing task per line.",
    )

    def save(self, *, user, organisation=None):
        organisation_name = self.cleaned_data["organisation_name"].strip()
        venue_name = self.cleaned_data["venue_name"].strip()
        if organisation is None:
            organisation = Organisation.objects.create(
                name=organisation_name,
                slug=slugify(organisation_name) or "organisation",
            )
        venue = Venue.objects.create(
            organisation=organisation,
            name=venue_name,
            slug=self.cleaned_data.get("venue_slug") or slugify(venue_name) or "venue",
            default_shift_start_time=self.cleaned_data.get("default_shift_start_time"),
            default_shift_end_time=self.cleaned_data.get("default_shift_end_time"),
            low_stock_buffer_percent=self.cleaned_data["low_stock_buffer_percent"],
            opening_handover_prompt="Opening checks complete and cellar/service prep confirmed.",
            closing_handover_prompt="Closing checks complete and handover notes recorded.",
        )
        VenueMembership.objects.create(
            venue=venue,
            user=user,
            role=StaffProfile.Role.LANDLORD if user.is_superuser else StaffProfile.Role.MANAGER,
            is_active=True,
            is_default=True,
            notify_on_shift_assignment=True,
            job_title=user.staff_profile.job_title,
        )

        for raw_name in self.cleaned_data.get("supplier_names", "").splitlines():
            supplier_name = raw_name.strip()
            if supplier_name:
                venue.suppliers.create(name=supplier_name)

        for sort_order, raw_title in enumerate(
            self.cleaned_data.get("opening_checklist_items", "").splitlines(),
            start=1,
        ):
            title = raw_title.strip()
            if title:
                ChecklistTemplate.objects.create(
                    venue=venue,
                    title=title,
                    checklist_type=Checklist.ChecklistType.OPENING,
                    sort_order=sort_order,
                )

        for sort_order, raw_title in enumerate(
            self.cleaned_data.get("closing_checklist_items", "").splitlines(),
            start=1,
        ):
            title = raw_title.strip()
            if title:
                ChecklistTemplate.objects.create(
                    venue=venue,
                    title=title,
                    checklist_type=Checklist.ChecklistType.CLOSING,
                    sort_order=sort_order,
                )

        return venue


class VenueInviteForm(forms.ModelForm):
    expires_in_days = forms.IntegerField(min_value=1, max_value=30, initial=7)

    class Meta:
        model = VenueInvite
        fields = [
            "email",
            "role",
            "job_title",
            "notify_on_shift_assignment",
        ]

    def save(self, *, venue, invited_by):
        invite = super().save(commit=False)
        invite.venue = venue
        invite.invited_by = invited_by
        invite.token = secrets.token_urlsafe(24)
        invite.expires_at = timezone.now() + timedelta(days=self.cleaned_data["expires_in_days"])
        invite.is_active = True
        invite.save()
        return invite


class VenueInviteAcceptForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    username = forms.CharField(max_length=150)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        if password1:
            try:
                validate_password(password1)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned_data

    def save(self, *, invite):
        user = User.objects.create_user(
            username=self.cleaned_data["username"],
            first_name=self.cleaned_data.get("first_name", "").strip(),
            last_name=self.cleaned_data.get("last_name", "").strip(),
            email=invite.email,
            password=self.cleaned_data["password1"],
        )
        profile = user.staff_profile
        profile.role = invite.role
        profile.job_title = invite.job_title
        profile.notify_on_shift_assignment = invite.notify_on_shift_assignment
        profile.save()
        VenueMembership.objects.update_or_create(
            venue=invite.venue,
            user=user,
            defaults={
                "role": invite.role,
                "job_title": invite.job_title,
                "notify_on_shift_assignment": invite.notify_on_shift_assignment,
                "is_active": True,
                "is_default": True,
                "invited_by": invite.invited_by,
            },
        )
        invite.accepted_by = user
        invite.accepted_at = timezone.now()
        invite.is_active = False
        invite.save(update_fields=["accepted_by", "accepted_at", "is_active", "updated_at"])
        return user
