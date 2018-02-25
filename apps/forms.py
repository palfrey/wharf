from django import forms

class ConfigForm(forms.Form):
    key = forms.CharField(label='key', max_length=100)
    value = forms.CharField(label='value', max_length=300)

class CreateAppForm(forms.Form):
    name = forms.CharField(label='App name', max_length=100)

class CreateDomainForm(forms.Form):
    name = forms.CharField(label='Domain name', max_length=100)