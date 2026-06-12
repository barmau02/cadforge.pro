import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

export interface PrintBed {
  widthMm: number;
  depthMm: number;
  heightMm: number;
  label?: string | null;
}

const DEFAULT_BED: PrintBed = { widthMm: 260, depthMm: 260, heightMm: 260 };

function addPrintBed(scene: THREE.Scene, bed: PrintBed) {
  const { widthMm: w, depthMm: d, heightMm: h } = bed;
  const cx = w / 2;
  const cz = d / 2;

  const grid = new THREE.GridHelper(Math.max(w, d), Math.round(Math.max(w, d) / 10), 0x2dd4bf, 0x1a1a1a);
  grid.position.set(cx, 0, cz);
  scene.add(grid);

  const bedFill = new THREE.Mesh(
    new THREE.PlaneGeometry(w, d),
    new THREE.MeshStandardMaterial({
      color: 0x0f766e,
      transparent: true,
      opacity: 0.08,
      side: THREE.DoubleSide,
    }),
  );
  bedFill.rotation.x = -Math.PI / 2;
  bedFill.position.set(cx, 0.01, cz);
  scene.add(bedFill);

  const borderPoints = [
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(w, 0, 0),
    new THREE.Vector3(w, 0, d),
    new THREE.Vector3(0, 0, d),
    new THREE.Vector3(0, 0, 0),
  ];
  const border = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(borderPoints),
    new THREE.LineBasicMaterial({ color: 0x2dd4bf }),
  );
  scene.add(border);

  const volumePoints = [
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(w, 0, 0),
    new THREE.Vector3(w, 0, d),
    new THREE.Vector3(0, 0, d),
    new THREE.Vector3(0, h, 0),
    new THREE.Vector3(w, h, 0),
    new THREE.Vector3(w, h, d),
    new THREE.Vector3(0, h, d),
  ];
  const volumeEdges = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
  ];
  for (const [a, b] of volumeEdges) {
    const edge = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([volumePoints[a], volumePoints[b]]),
      new THREE.LineBasicMaterial({ color: 0x3f3f46, transparent: true, opacity: 0.55 }),
    );
    scene.add(edge);
  }

  return { cx, cz, maxDim: Math.max(w, d, h) };
}

function placeMeshOnBed(mesh: THREE.Mesh, bed: PrintBed) {
  mesh.rotation.x = -Math.PI / 2;
  mesh.updateMatrixWorld(true);

  const box = new THREE.Box3().setFromObject(mesh);
  mesh.position.y -= box.min.y;
  mesh.updateMatrixWorld(true);

  const placed = new THREE.Box3().setFromObject(mesh);
  mesh.position.x += bed.widthMm / 2 - (placed.min.x + placed.max.x) / 2;
  mesh.position.z += bed.depthMm / 2 - (placed.min.z + placed.max.z) / 2;
  mesh.updateMatrixWorld(true);

  const finalBox = new THREE.Box3().setFromObject(mesh);
  const overflow =
    finalBox.min.x < -0.5
    || finalBox.max.x > bed.widthMm + 0.5
    || finalBox.min.z < -0.5
    || finalBox.max.z > bed.depthMm + 0.5
    || finalBox.max.y > bed.heightMm + 0.5;

  return { box: finalBox, overflow };
}

function frameCamera(
  camera: THREE.PerspectiveCamera,
  controls: OrbitControls,
  bed: PrintBed,
  meshBox: THREE.Box3 | null,
) {
  const cx = bed.widthMm / 2;
  const cz = bed.depthMm / 2;
  const span = Math.max(bed.widthMm, bed.depthMm, bed.heightMm);
  camera.position.set(cx + span * 0.55, span * 0.75, cz + span * 0.85);
  camera.near = span / 500;
  camera.far = span * 20;
  camera.updateProjectionMatrix();
  controls.target.set(cx, Math.min(bed.heightMm * 0.2, meshBox ? meshBox.max.y * 0.5 : bed.heightMm * 0.15), cz);
  controls.update();
}

export function ModelViewer({
  stlUrl,
  fallbackImage,
  printBed,
}: {
  stlUrl: string | null;
  fallbackImage: string | null;
  printBed?: PrintBed | null;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [overflow, setOverflow] = useState(false);
  const bed = printBed ?? DEFAULT_BED;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    setError(null);
    setOverflow(false);
    setLoading(Boolean(stlUrl));

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    scene.add(new THREE.AmbientLight(0xffffff, 0.45));
    const key = new THREE.DirectionalLight(0xffffff, 1.0);
    key.position.set(1, 1, 1.5);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x6b7280, 0.4);
    fill.position.set(-1.5, -0.5, -1);
    scene.add(fill);

    addPrintBed(scene, bed);
    frameCamera(camera, controls, bed, null);

    let mesh: THREE.Mesh | null = null;
    let disposed = false;

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    const onMeshLoaded = (geometry: THREE.BufferGeometry) => {
      if (disposed) return;
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();

      const material = new THREE.MeshStandardMaterial({
        color: 0x6b7280,
        metalness: 0.1,
        roughness: 0.65,
      });
      mesh = new THREE.Mesh(geometry, material);
      scene.add(mesh);

      const { box, overflow: tooBig } = placeMeshOnBed(mesh, bed);
      if (tooBig) {
        (mesh.material as THREE.MeshStandardMaterial).color.setHex(0xd97706);
        setOverflow(true);
      }
      frameCamera(camera, controls, bed, box);
      setLoading(false);
    };

    if (stlUrl) {
      new STLLoader().load(
        stlUrl,
        onMeshLoaded,
        undefined,
        () => {
          if (!disposed) {
            setLoading(false);
            setError("Could not load 3D mesh — build a model first, then refresh.");
          }
        },
      );
    } else {
      setLoading(false);
    }

    let raf = 0;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      if (mesh) {
        mesh.geometry.dispose();
        (mesh.material as THREE.Material).dispose();
      }
      scene.traverse((obj) => {
        if (obj instanceof THREE.Line || obj instanceof THREE.GridHelper) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose());
          else obj.material?.dispose();
        }
        if (obj instanceof THREE.Mesh && obj !== mesh) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      renderer.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, [stlUrl, bed.widthMm, bed.depthMm, bed.heightMm]);

  if (error) {
    return (
      <div className="preview-empty">
        <p>{error}</p>
        {fallbackImage ? (
          <img src={fallbackImage} alt="FreeCAD model preview" className="model-viewer-fallback" />
        ) : null}
      </div>
    );
  }

  const bedLabel = `${Math.round(bed.widthMm)}×${Math.round(bed.depthMm)}×${Math.round(bed.heightMm)} mm`;

  return (
    <div className="model-viewer" ref={mountRef}>
      {loading && <div className="model-viewer-loading">Loading mesh…</div>}
      {!stlUrl && !loading && (
        <div className="model-viewer-empty-hint">Build a model — it will appear centered on the bed</div>
      )}
      <div className="model-viewer-bed-label">
        {bed.label ? `${bed.label} · ` : ""}
        Bed {bedLabel}
      </div>
      {overflow && (
        <div className="model-viewer-bed-warning">Model exceeds printable volume</div>
      )}
    </div>
  );
}
