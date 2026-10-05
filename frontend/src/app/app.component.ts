import { AfterViewInit, Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import * as L from 'leaflet';
import { ApiService, Club, Recommendation, Summary } from './api.service';

@Component({selector: 'app-root', standalone: true, imports: [CommonModule, FormsModule], templateUrl: './app.component.html', styleUrl: './app.component.css'})
export class AppComponent implements OnInit, AfterViewInit, OnDestroy {
  private readonly api = inject(ApiService);
  summary: Summary = { total: 0, restaurants: 0, clubs: 0, bars: 0, cafes: 0 };
  clubs: Club[] = [];
  recommendations: Recommendation[] = [];
  totalRecommendations = 0;
  currentPage = 1;
  totalPages = 0;
  readonly pageSize = 10;
  visitMode: 'now' | 'custom' = 'now';
  visitTime = '23:00';
  openOnly = false;
  currentLocation: {lat: number; lon: number} | null = null;
  locationMessage = '';
  selectedClubId: number | null = null;
  maxDistance = 3000;
  loading = true;
  error = '';
  private map?: L.Map;
  private readonly markers = L.layerGroup();

  ngOnInit(): void {
    this.api.summary().subscribe({next: (value) => this.summary = value, error: () => this.error = 'The API is not available yet.'});
    this.api.clubs().subscribe({next: (value) => {this.clubs = value; this.loadRecommendations();}, error: () => this.error = 'Load the ETL first, then refresh this page.'});
  }

  ngAfterViewInit(): void {
    this.map = L.map('map').setView([45.764, 4.8357], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '&copy; OpenStreetMap contributors'}).addTo(this.map);
    this.markers.addTo(this.map);
    this.updateMap();
  }

  ngOnDestroy(): void { this.map?.remove(); }
  onFilterChange(): void { this.currentPage = 1; this.loadRecommendations(); }
  get selectedVisitTime(): string | null { return this.visitMode === 'custom' ? this.visitTime : null; }
  useCurrentLocation(): void {
    if (!navigator.geolocation) { this.locationMessage = 'Geolocation is not available in this browser.'; return; }
    navigator.geolocation.getCurrentPosition(
      (position) => { this.currentLocation = {lat: position.coords.latitude, lon: position.coords.longitude}; this.selectedClubId = null; this.currentPage = 1; this.locationMessage = 'Using your current location.'; this.loadRecommendations(); },
      () => this.locationMessage = 'Location permission was not granted.'
    );
  }
  previousPage(): void { if (this.currentPage > 1) { this.currentPage--; this.loadRecommendations(); } }
  nextPage(): void { if (this.currentPage < this.totalPages) { this.currentPage++; this.loadRecommendations(); } }

  loadRecommendations(): void {
    this.loading = true;
    this.api.recommendations(this.selectedClubId, this.maxDistance, this.currentPage, this.pageSize, this.currentLocation, this.selectedVisitTime, this.openOnly).subscribe({
      next: (value) => {this.recommendations = value.items; this.totalRecommendations = value.total; this.totalPages = value.pages; this.loading = false; this.updateMap();},
      error: () => {this.error = 'Could not load recommendations.'; this.loading = false;}
    });
  }

  private updateMap(): void {
    if (!this.map) return;
    this.markers.clearLayers();
    const club = this.clubs.find((item) => item.id === this.selectedClubId);
    if (club) L.marker([club.latitude, club.longitude]).bindPopup(`<b>${club.name}</b><br>Selected club`).addTo(this.markers);
    if (this.currentLocation) L.marker([this.currentLocation.lat, this.currentLocation.lon]).bindPopup('<b>Your current location</b>').addTo(this.markers);
    for (const item of this.recommendations) {
      L.circleMarker([item.latitude, item.longitude], {radius: 7, color: '#e879f9', fillOpacity: 0.85}).bindPopup(`<b>${item.restaurant_name}</b><br>${item.walking_minutes} min walk`).addTo(this.markers);
    }
  }
}
