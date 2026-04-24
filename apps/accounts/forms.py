from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import StaffProfile


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

    def save(self):
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

    def __init__(self, *args, user_instance, allowed_role_values=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_instance = user_instance
        self.allowed_role_values = set(allowed_role_values or [])
        if self.allowed_role_values:
            self.fields["role"].choices = [
                choice for choice in StaffProfile.Role.choices if choice[0] in self.allowed_role_values
            ]
        self.fields["first_name"].initial = user_instance.first_name
        self.fields["last_name"].initial = user_instance.last_name
        self.fields["email"].initial = user_instance.email

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

        return profile
