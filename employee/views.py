from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader
from django.urls import reverse
from .models import employee


def index(request):
    myemployee = employee.objects.all().values()
    template = loader.get_template('index.html')
    context = {
        'myemployee': myemployee,
    }
    return HttpResponse(template.render(context, request))


def add(request):
    template = loader.get_template('add.html')
    return HttpResponse(template.render({}, request))


def addrecord(request):
    x = request.POST['first']
    y = request.POST['last']
    emp = employee(firstname=x, lastname=y)
    emp.save()
    return HttpResponseRedirect(reverse('index'))


def delete(request, id):
    emp = employee.objects.get(id=id)
    emp.delete()
    return HttpResponseRedirect(reverse('index'))


def update(request, id):
    myemployee = employee.objects.get(id=id)
    template = loader.get_template('update.html')
    context = {
        'myemployee': myemployee,
    }
    return HttpResponse(template.render(context, request))


def updaterecord(request, id):
    first = request.POST['first']
    last = request.POST['last']
    emp = employee.objects.get(id=id)
    emp.firstname = first
    emp.lastname = last
    emp.save()
    return HttpResponseRedirect(reverse('index'))