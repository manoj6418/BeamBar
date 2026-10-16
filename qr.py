# Third Party Library
import Quartz
from AppKit import (
    NSBitmapImageRep,
    NSCIImageRep,
    NSColor,
    NSCompositingOperationSourceOver,
    NSGraphicsContext,
    NSImage,
    NSImageInterpolationNone,
    NSMakeRect,
    NSPNGFileType,
    NSRectFill,
)
from Foundation import NSData


def qr_image(text, size=240, margin=0.08, level='M'):
    """A QR code for `text` as an NSImage of `size` points, black on white with a quiet margin.

    Drawn by Core Image, so no extra package is needed; scaled without smoothing so
    the squares stay sharp for phone cameras.
    """
    data = text.encode('utf-8')
    generator = Quartz.CIFilter.filterWithName_('CIQRCodeGenerator')
    generator.setValue_forKey_(NSData.dataWithBytes_length_(data, len(data)), 'inputMessage')
    generator.setValue_forKey_(level, 'inputCorrectionLevel')
    code = NSCIImageRep.imageRepWithCIImage_(generator.outputImage())

    margin = size * margin
    image = NSImage.alloc().initWithSize_((size, size))
    image.lockFocus()
    NSGraphicsContext.currentContext().setImageInterpolation_(NSImageInterpolationNone)
    NSColor.whiteColor().set()
    NSRectFill(NSMakeRect(0, 0, size, size))
    code.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(margin, margin, size - 2 * margin, size - 2 * margin),
        NSMakeRect(0, 0, code.size().width, code.size().height),
        NSCompositingOperationSourceOver, 1.0, True, None,
    )
    image.unlockFocus()
    return image


def png_bytes(image):
    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    return bytes(rep.representationUsingType_properties_(NSPNGFileType, {}))


def save_png(image, path):
    rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
    rep.representationUsingType_properties_(NSPNGFileType, {}).writeToFile_atomically_(path, True)
