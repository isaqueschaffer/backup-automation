"""Grade do Dashboard por Cliente (schema 3): migração do schema 2 e normalização das posições."""
from services.dashboards.layout import COLUNAS, DashboardLayout, layout_padrao


def _w(id_, largura, altura, **extra):
    return {"id": id_, "tipo": "texto", "largura": largura, "altura": altura, "config": {}, **extra}


def _caixas(layout):
    return {w.id: (w.x, w.y, w.largura, w.altura) for w in layout.widgets}


def test_migra_schema_2_mantendo_a_aparencia():
    layout = DashboardLayout.model_validate({
        "schema_version": 2,
        "widgets": [_w("a", 12, 3), _w("b", 6, 6), _w("c", 6, 4), _w("d", 4, 2)],
    })
    assert layout.schema_version == 3
    # a ocupa a linha toda; b e c lado a lado; d abaixo de c (c é mais baixo que b)
    assert _caixas(layout) == {
        "a": (0, 0, 24, 6),
        "b": (0, 6, 12, 12),
        "c": (12, 6, 12, 8),
        "d": (12, 14, 8, 4),
    }


def test_widget_sem_posicao_vai_para_o_primeiro_lugar_livre():
    layout = DashboardLayout.model_validate({
        "widgets": [_w("a", 12, 6, x=0, y=0), _w("novo", 8, 4)],
    })
    assert _caixas(layout)["novo"] == (12, 0, 8, 4)


def test_desfaz_sobreposicao_e_sobe_os_widgets():
    layout = DashboardLayout.model_validate({
        "widgets": [_w("a", 24, 6, x=0, y=10), _w("b", 12, 6, x=6, y=12)],
    })
    caixas = _caixas(layout)
    assert caixas["a"] == (0, 0, 24, 6)
    assert caixas["b"] == (6, 6, 12, 6)
    assert [w.id for w in layout.widgets] == ["a", "b"]


def test_x_e_limitado_a_largura_da_grade():
    layout = DashboardLayout.model_validate({"widgets": [_w("a", 10, 4, x=20, y=0)]})
    w = layout.widgets[0]
    assert w.x + w.largura == COLUNAS


def test_layout_padrao_sem_sobreposicao():
    caixas = list(_caixas(layout_padrao()).values())
    for i, (x1, y1, l1, a1) in enumerate(caixas):
        for x2, y2, l2, a2 in caixas[i + 1:]:
            assert not (x1 < x2 + l2 and x2 < x1 + l1 and y1 < y2 + a2 and y2 < y1 + a1)
