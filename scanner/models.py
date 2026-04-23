from django.db import models

class ScanHistory(models.Model):
    # ImageField automatically handles saving the actual photo file
    image = models.ImageField(upload_to='leaf_scans/')
    
    # CharField is for short text, IntegerField is for numbers
    disease_name = models.CharField(max_length=200)
    confidence_score = models.IntegerField()
    
    # JSONField is perfect for storing our array of treatments!
    treatments = models.JSONField()
    
    # Automatically saves the exact date and time the scan was taken
    created_at = models.DateTimeField(auto_now_add=True)

    # This just makes it look pretty in the Django admin panel later
    def __str__(self):
        return f"{self.disease_name} - {self.created_at.strftime('%Y-%m-%d')}"