package uav.sdk.keyvalue.value.flightcontroller;
public final class LEDsSettings {
    private final Boolean front,status,rear,navigation;
    public LEDsSettings(Boolean front,Boolean status,Boolean rear,Boolean navigation) {
        this.front=front; this.status=status; this.rear=rear; this.navigation=navigation;
    }
    public Boolean getFrontLEDsOn() { return front; }
    public Boolean getStatusIndicatorOn() { return status; }
    public Boolean getRearLEDsOn() { return rear; }
    public Boolean getNavigationEnabled() { return navigation; }
}
