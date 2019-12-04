from django import forms
from django.contrib.auth.forms import AuthenticationForm, UsernameField


class ConfigForm(forms.Form):
    key = forms.CharField(label='key', max_length=100)
    value = forms.CharField(label='value', max_length=300)


class CreateAppForm(forms.Form):
    name = forms.CharField(label='App name', max_length=100)


class CreateDomainForm(forms.Form):
    name = forms.CharField(label='Domain name', max_length=100)


class LoginForm(AuthenticationForm):

    username = UsernameField(widget=forms.TextInput(
        attrs={'autofocus': True, 'class': 'form-control', 'placeholder': 'Username'})
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
    )
