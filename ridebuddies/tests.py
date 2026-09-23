from django.test import SimpleTestCase


class StartseiteTest(SimpleTestCase):
    def test_startseite_antwortet(self):
        antwort = self.client.get('/')
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, 'Ridebuddies')
