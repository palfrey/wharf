from django import forms

class ConfigForm(forms.Form):
    key = forms.CharField(label='key', max_length=100)
    value = forms.CharField(label='value', max_length=300)