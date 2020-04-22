from django import forms
from django.contrib.auth.forms import AuthenticationForm, UsernameField


class ConfigForm(forms.Form):
    key = forms.CharField(
        label='key',
        max_length=100
    )
    value = forms.CharField(
        label='value',
        max_length=300
    )


class ConfigFormBulk(forms.Form):
    userInput = forms.CharField(
        widget=forms.Textarea(
            attrs={
                'class': 'form-control global-config-bulk',
                'placeholder': 'The format is key:data. Add a new line to multiple variables'
            }
        ),
        label=''
    )


class ConfigRemoveForm(forms.Form):

    configKeyName = forms.CharField(
        label='Env variable key (name)'
    )


class BuildpackAddForm(forms.Form):

    buildpack_url = forms.CharField(
        label='Buildpack URL',
    )
    buildpack_type = forms.CharField(
        label='Buildpack type',
    )
    buildpack_index = forms.CharField(
        label='Buildpack index',
    )


class BuildpackRemoveForm(forms.Form):

    buildpack_url = forms.CharField(
        label='Buildpack URL'
    )


class CreateAppForm(forms.Form):
    name = forms.CharField(
        label='Name',
        max_length=100,
        widget=forms.TextInput(
            attrs={
                'autocomplete': 'new-password',
                'class': 'form-control',
            }
        ),
        # validators=[RegexValidator('^(\w+\d+|\d+\w+)+$', message="Try another app name")],
    )


class CreateDomainForm(forms.Form):
    name = forms.CharField(
        label='Domain name',
        max_length=100
    )


class LoginForm(AuthenticationForm):

    username = UsernameField(
        widget=forms.TextInput(
            attrs={
                'autofocus': True,
                'class': 'form-control',
                'placeholder': 'Username'
            }
        )
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Password'
            }
        ),
    )
