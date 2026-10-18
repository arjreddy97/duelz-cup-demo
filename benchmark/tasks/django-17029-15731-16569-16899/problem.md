Several problems have been reported against this repository. Each is described below under its own heading. Fix all of them.

## Issue 1

inspect.signature() returns incorrect signature on manager methods.
Description
	 
		(last modified by Shiva Kumar)
	 
inspect.signature returns incorrect signature information when used on queryset methods
import inspect
from django.db import models
class Person(models.Model):
	name = models.CharField(max_length=100)
print(inspect.signature(Person.objects.bulk_create))
# actual: (*args, **kwargs)
# expected: (objs, batch_size=None, ignore_conflicts=False)
ipython and jupyter seem to internally use inspect.signature to show documentation when using the <obj>? command and they too show incorrect signature information:
 
The issue is due to the code at ​https://github.com/django/django/blob/fe2e1478464846638082219c933a4302e5cf3037/django/db/models/manager.py#L84
Although we are ensuring the decorated method has the right name and docstring on lines 87 and 88, complete metadata is not copied.
The fix is to use functools.wraps instead of manually assigning name and docstring. wraps will take care of all the metadata and inspect.signature will return the expected output.
If the bug is acknowledged please assign the ticket to me, I would like to raise a PR for this.

## Issue 2

Formsets' add_fields() method fails in some circumstances if the argument index is None.
Description
	
Formsets' add_fields() method fails in some circumstances if the argument index is None.
When a FormSet has the attributes self.can_delete == True and self.can_delete_extra == False, calling the add_fields() method on that FormSet fails if the argument index is None. This occurs for example when calling FormSet.empty_form(). The result is that the method raises the exception TypeError: '<' not supported between instances of 'NoneType' and 'int'. 
Code example:
MyFormSet = forms.formset_factory(
	form=MyForm,
	can_delete=True,
	can_delete_extra=False,
)
my_formset = MyFormSet(
	initial=None,
)
print(my_formset.empty_form)
The reason this happens is that in in line 493 of [django.forms.formsets](​https://github.com/django/django/blob/main/django/forms/formsets.py) index is compared to initial_form_count:
if self.can_delete and (self.can_delete_extra or index < initial_form_count):
Checking for index not None should fix the issue:
if self.can_delete and (self.can_delete_extra or (index is not None and index < initial_form_count)):
How to Reproduce
A self-contained example to reproduce this bug is as follows:
#!/usr/bin/env python3
import os
import django
from django import forms
class MyForm(forms.Form):
	my_field = forms.CharField()
if __name__ == "__main__":
	settings_file = os.path.splitext(os.path.basename(__file__))[0]
	django.conf.settings.configure(
		DEBUG=True,
		MIDDLEWARE_CLASSES=[],
		ROOT_URLCONF=settings_file,
	)
	django.setup()
	MyFormSet = forms.formset_factory(
		form=MyForm,
		can_delete=True,
		can_delete_extra=False,
	)
	my_formset = MyFormSet(
		initial=None,
	)
	print(my_formset.empty_form)

## Issue 3

ModelAdmin: Error message for readonly_fields's check does not include the field name
Description
	
When subclassing a ModelAdmin, the current error message for the readonly_fields would indicate the index of the value at fault but it will not include the field's name (from the test suite):
The value of 'readonly_fields[0]' is not a callable, an attribute of 'CityInline', or an attribute of 'admin_checks.City'.
Other fields like list_editable, raw_id_fields, list_display, etc. would also include this value:
The value of 'list_editable[0]' refers to 'original_release', which is not contained in 'list_display'.
It would be good if we can unify this and include the field name in the readonly_fields checks, it also eases the understanding of the error when using the framework.

## Issue 4

Apps.clear_cache() does not clear get_swappable_settings_name cache.
Description
	
We use apps.clear_cache() in django-stubs to be able to reset the previous state on consequential mypy runs.
Code: ​https://github.com/typeddjango/django-stubs/pull/1601/files#diff-c49d8fe2cd0a58fad3c36ab3a88c7745e9622f3098e60cd512953eb17b8a1994R63-R64
But, looks like we don't clear all the object's cache this way, because get_swappable_settings_name (which is a functools._lru_cache_wrapper) is not cleared.
I think that this is not correct. .clear_cache doc states: Clear all internal caches, for methods that alter the app registry.
Looks like that is not the case.
I propose to add: self.get_swappable_settings_name.cache_clear() line to def clear_cache.
If others agree, I will make a PR.
Original discussion: ​https://github.com/typeddjango/django-stubs/pull/1601#discussion_r1246344533