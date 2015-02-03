from django.db import models
from djangae.test import TestCase
from djangae.contrib import sleuth

from djangae.contrib.pagination import (
    paginated_model,
    Paginator,
    PaginationOrderingRequired
)

from .paginator import queryset_identifier, _get_marker

@paginated_model(orderings=[
    ("first_name",),
    ("last_name",),
    ("first_name", "last_name"),
    ("first_name", "-last_name")
])
class TestUser(models.Model):
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200)

    def __unicode__(self):
        return u" ".join([self.first_name, self.last_name])

class PaginatedModelTests(TestCase):
    def test_fields_added_correctly(self):
        self.assertIsNotNone(TestUser._meta.get_field("pagination_first_name"))
        self.assertIsNotNone(TestUser._meta.get_field("pagination_last_name"))
        self.assertIsNotNone(TestUser._meta.get_field("pagination_first_name_last_name"))
        self.assertIsNotNone(TestUser._meta.get_field("pagination_first_name_neg_last_name"))


    def test_precalculate_field_values(self):
        user = TestUser.objects.create(pk=1, first_name="Luke", last_name="Benstead")

        self.assertEqual(u"Luke\x001", user.pagination_first_name)
        self.assertEqual(u"Benstead\x001", user.pagination_last_name)
        self.assertEqual(u"Luke\x00Benstead\x001", user.pagination_first_name_last_name)

        reversed_last_name = "".join([ unichr(0xffff - ord(x)) for x in "Benstead" ])

        self.assertEqual(u"Luke\x00{}\x001".format(reversed_last_name), user.pagination_first_name_neg_last_name)


class DatastorePaginatorTests(TestCase):
    def setUp(self):
        super(DatastorePaginatorTests, self).setUp()

        self.u1 = TestUser.objects.create(id=1, first_name="A", last_name="A")
        self.u2 = TestUser.objects.create(id=2, first_name="A", last_name="B")
        self.u3 = TestUser.objects.create(id=3, first_name="B", last_name="A")
        self.u4 = TestUser.objects.create(id=4, first_name="B", last_name="B")

    def test_count_up_to(self):
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1, readahead=2)

        self.assertEqual(2, paginator.count)

        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1)

        self.assertEqual(4, paginator.count)

    def test_count_reads_ahead(self):
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1, readahead=2)

        self.assertEqual(2, paginator.count)

        paginator.page(3)

        self.assertEqual(4, paginator.count)


    def test_page_jump_updates_count_correctly(self):
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1, readahead=1)
        self.assertEqual(1, paginator.count)
        paginator.page(3)
        self.assertEqual(4, paginator.count)

    def test_that_marker_is_read(self):
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1, readahead=1)
        paginator.page(2)

        with sleuth.watch("djangae.contrib.pagination.paginator._get_marker") as get_marker:
            paginator.page(4)

            self.assertTrue(get_marker.called)
            self.assertIsNotNone(get_marker.call_returns[0][0])
            self.assertEqual(1, get_marker.call_returns[0][1])

    def test_that_readahead_stores_markers(self):
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1, readahead=4)

        expected_markers = [ None ] + list(TestUser.objects.all().order_by("first_name").values_list(paginator.field_required, flat=True))[:3]

        paginator.page(1)

        query_id = queryset_identifier(paginator.object_list)

        actual_markers = []
        for i in xrange(1, 5):
            actual_markers.append(_get_marker(paginator.object_list.model, query_id, i)[0])

        self.assertEqual(expected_markers, actual_markers)

        # Now change the per page number
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 2, readahead=4)

        all_markers = list(TestUser.objects.all().order_by("first_name").values_list(paginator.field_required, flat=True))
        expected_markers = [ None, all_markers[1] ]

        paginator.page(1)

        query_id = queryset_identifier(paginator.object_list)

        actual_markers = []
        for i in xrange(1, 3):
            actual_markers.append(_get_marker(paginator.object_list.model, query_id, i)[0])

        self.assertEqual(expected_markers, actual_markers)

    def test_pages_correct(self):
        paginator = Paginator(TestUser.objects.all().order_by("first_name"), 1) # 1 item per page

        self.assertEqual("A", paginator.page(1).object_list[0].first_name)
        self.assertEqual("A", paginator.page(2).object_list[0].first_name)
        self.assertEqual("B", paginator.page(3).object_list[0].first_name)
        self.assertEqual("B", paginator.page(4).object_list[0].first_name)

        paginator = Paginator(TestUser.objects.all().order_by("first_name", "last_name"), 1) # 1 item per page
        self.assertEqual(self.u1, paginator.page(1).object_list[0])
        self.assertEqual(self.u2, paginator.page(2).object_list[0])
        self.assertEqual(self.u3, paginator.page(3).object_list[0])
        self.assertEqual(self.u4, paginator.page(4).object_list[0])

        paginator = Paginator(TestUser.objects.all().order_by("first_name", "-last_name"), 1) # 1 item per page
        self.assertEqual(self.u2, paginator.page(1).object_list[0])
        self.assertEqual(self.u1, paginator.page(2).object_list[0])
        self.assertEqual(self.u4, paginator.page(3).object_list[0])
        self.assertEqual(self.u3, paginator.page(4).object_list[0])

        paginator = Paginator(TestUser.objects.all().order_by("-first_name"), 1) # 1 item per page
        self.assertEqual(self.u4, paginator.page(1).object_list[0])
        self.assertEqual(self.u3, paginator.page(2).object_list[0])
        self.assertEqual(self.u2, paginator.page(3).object_list[0])
        self.assertEqual(self.u1, paginator.page(4).object_list[0])

        with self.assertRaises(PaginationOrderingRequired):
            paginator = Paginator(TestUser.objects.all().order_by("-first_name", "last_name"), 1) # 1 item per page
            list(paginator.page(1).object_list)
