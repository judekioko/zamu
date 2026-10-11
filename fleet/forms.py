from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Expense, Remittance, Vehicle

DATE = forms.DateInput(attrs={'type': 'date'})


class VehicleForm(forms.ModelForm):
    location_name = forms.CharField(max_length=80, required=False,
                                    label='Based at (route / stage / town)')

    class Meta:
        model = Vehicle
        fields = ['reg', 'kind', 'nickname', 'driver_name', 'driver_phone', 'daily_target',
                  'start_date', 'active']
        widgets = {'start_date': DATE}

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        if self.instance.pk and self.instance.location:
            self.fields['location_name'].initial = self.instance.location.name
        self.order_fields(['reg', 'kind', 'nickname', 'location_name', 'driver_name', 'driver_phone',
                           'daily_target', 'start_date', 'active'])

    def clean_reg(self):
        reg = self.cleaned_data['reg'].strip().upper()
        clash = Vehicle.objects.filter(owner=self.owner, reg=reg).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('You already have this vehicle.')
        return reg


class RemittanceForm(forms.ModelForm):
    class Meta:
        model = Remittance
        fields = ['date', 'amount', 'note']
        widgets = {'date': DATE}

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > date.today():
            raise forms.ValidationError('That date is in the future.')
        return d


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date', 'category', 'amount', 'note']
        widgets = {'date': DATE}


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username',)


class MoveForm(forms.Form):
    to_name = forms.CharField(max_length=80, label='Move to')
    date = forms.DateField(widget=DATE, initial=date.today)
    note = forms.CharField(max_length=120, required=False)

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > date.today():
            raise forms.ValidationError('That date is in the future.')
        return d
