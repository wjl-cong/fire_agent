export const setPointStyle = ({point,radius,fill}) => {
  point.setStyle(new ol.style.Style({
    image:new ol.style.Circle({
      radius:radius,
      fill:new ol.style.Fill({
        color:fill
      })
    })
  }))
}
