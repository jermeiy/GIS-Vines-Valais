from django.db import models
import json

class Parcelle(models.Model):
    """Model for vine parcels in Valais region"""
    nom = models.CharField(max_length=200, default="Parcelle")
    score = models.FloatField(default=0.5)  # Score for prioritization (0 to 1)
    geometry_geojson = models.JSONField(default=dict, blank=True)  # Store GeoJSON geometry
    latitude = models.FloatField(default=46.23)
    longitude = models.FloatField(default=7.36)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Parcelle"
        verbose_name_plural = "Parcelles"
    
    def __str__(self):
        return f"{self.nom} (score: {self.score})"
    
    def to_geojson_feature(self):
        """Convert to GeoJSON feature format"""
        return {
            "type": "Feature",
            "geometry": self.geometry_geojson or {
                "type": "Point",
                "coordinates": [self.longitude, self.latitude]
            },
            "properties": {
                "id": self.id,
                "nom": self.nom,
                "score": self.score,
            }
        }
