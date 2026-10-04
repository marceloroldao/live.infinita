extends RefCounted
# Bounded colliders share the exact transforms of materialized nature instances.
static func sync(batch: MultiMeshInstance3D, transforms: Array, trunks: bool = false) -> void:
    var container := batch.get_node_or_null("PhysicalInstances")
    if container == null:
        container = Node3D.new()
        container.name = "PhysicalInstances"
        batch.add_child(container)
    var count := transforms.size()
    for i in range(container.get_child_count(), count):
        var body := StaticBody3D.new()
        body.collision_layer = 1
        var collision := CollisionShape3D.new()
        body.add_child(collision)
        container.add_child(body)
    var bounds := batch.multimesh.mesh.get_aabb()
    for i in range(container.get_child_count()):
        var body: StaticBody3D = container.get_child(i)
        var collision: CollisionShape3D = body.get_child(0)
        collision.disabled = i >= count
        if i >= count:
            continue
        # Use the generator's CPU transform, never a same-frame render-server readback.
        body.transform = transforms[i]
        if trunks:
            var shape := CylinderShape3D.new()
            shape.radius = 0.42
            shape.height = maxf(2.0, bounds.size.y)
            collision.shape = shape
            collision.position = Vector3(0, bounds.get_center().y, 0)
        else:
            var shape := BoxShape3D.new()
            shape.size = bounds.size
            collision.shape = shape
            collision.position = bounds.get_center()

static func attach_model(model: Node3D, trunk: bool) -> void:
    if trunk:
        var body := StaticBody3D.new()
        var shape := CylinderShape3D.new()
        shape.radius = 0.45
        shape.height = 4.0
        var collision := CollisionShape3D.new()
        collision.shape = shape
        collision.position.y = 2.0
        body.add_child(collision)
        model.add_child(body)
    else:
        for child in model.get_children():
            if child is MeshInstance3D and child.mesh != null:
                var body := StaticBody3D.new()
                var bounds: AABB = child.mesh.get_aabb()
                var shape := BoxShape3D.new()
                shape.size = bounds.size
                var collision := CollisionShape3D.new()
                collision.shape = shape
                collision.position = bounds.get_center()
                body.add_child(collision)
                child.add_child(body)
            elif child is Node3D:
                attach_model(child, false)
